"""
CordCloud Auto Login + Daily Check-in
使用 CloakBrowser (Playwright兼容) + POP3 邮箱验证码
"""

import os
import re
import time
import poplib
import smtplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, formatdate
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# CloakBrowser 提供 Playwright 兼容 API
from cloakbrowser import launch, launch_persistent_context

# ── 配置 ────────────────────────────────────────────
load_dotenv()

CORDCLOUD_EMAIL = os.getenv("CORDCLOUD_EMAIL", "")
CORDCLOUD_PASSWORD = os.getenv("CORDCLOUD_PASSWORD", "")

# POP3 配置
POP3_HOST = os.getenv("POP3_HOST", "pop.example.com")
POP3_PORT = int(os.getenv("POP3_PORT", "995"))
POP3_USE_SSL = os.getenv("POP3_USE_SSL", "true").lower() == "true"
POP3_USERNAME = os.getenv("POP3_USERNAME", CORDCLOUD_EMAIL)
POP3_PASSWORD = os.getenv("POP3_PASSWORD", "")

# SMTP 配置（发送签到结果通知）
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"
SMTP_USERNAME = os.getenv("SMTP_USERNAME", CORDCLOUD_EMAIL)
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# 持久化配置
USE_PERSISTENT = os.getenv("USE_PERSISTENT_CONTEXT", "true").lower() == "true"
PROFILE_DIR = Path(os.getenv("PERSISTENT_PROFILE_DIR", "./cloak_profile"))
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

LOGIN_URL = "https://www.cordcloud.one/auth/login"
USER_URL = "https://www.cordcloud.one/user"

# 调试：保存每步 HTML
DEBUG_HTML_DIR = Path("./debug_html")
SAVE_HTML = os.getenv("SAVE_HTML", "true").lower() == "true"

# ── 调试工具 ─────────────────────────────────────

def save_page_state(page, step_name: str) -> str | None:
    """保存当前页面的 HTML 和截图，用于分析页面结构。返回截图路径。"""
    if not SAVE_HTML:
        return None
    DEBUG_HTML_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%H%M%S")
    html_path = DEBUG_HTML_DIR / f"{timestamp}_{step_name}.html"
    png_path = DEBUG_HTML_DIR / f"{timestamp}_{step_name}.png"
    try:
        html_path.write_text(page.content(), encoding="utf-8")
        print(f"[DEBUG] HTML 已保存: {html_path}")
    except Exception as e:
        print(f"[DEBUG] HTML 保存失败: {e}")
    try:
        page.screenshot(path=str(png_path), full_page=False)
        print(f"[DEBUG] 截图已保存: {png_path}")
        return str(png_path)
    except Exception as e:
        print(f"[DEBUG] 截图保存失败: {e}")
        return None


# ── SMTP 发送工具 ─────────────────────────────────────

def send_result_email(subject: str, body: str, image_path: str | None = None):
    """通过 SMTP 发送签到结果邮件（自己发给自己），可选附带截图"""
    if not SMTP_PASSWORD:
        print("[SMTP] 未配置 SMTP_PASSWORD，跳过邮件发送")
        return

    try:
        if image_path:
            msg = MIMEMultipart("related")
            msg["From"] = SMTP_USERNAME
            msg["To"] = CORDCLOUD_EMAIL
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

            # 文本部分
            text_part = MIMEText(body, "plain", "utf-8")
            msg.attach(text_part)

            # 图片附件
            with open(image_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="png")
                img.add_header("Content-Disposition", "attachment", filename=Path(image_path).name)
                msg.attach(img)
        else:
            msg = MIMEText(body, "plain", "utf-8")
            msg["From"] = SMTP_USERNAME
            msg["To"] = CORDCLOUD_EMAIL
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

        if SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            server.starttls()

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, [CORDCLOUD_EMAIL], msg.as_string())
        server.quit()
        print(f"[SMTP] ✅ 结果邮件已发送至 {CORDCLOUD_EMAIL}")
    except Exception as e:
        print(f"[SMTP] ❌ 邮件发送失败: {e}")


# ── POP3 邮箱工具 ─────────────────────────────────────

def decode_mime_header(header_value):
    """解码 MIME 编码的邮件头"""
    if header_value is None:
        return ""
    parts = decode_header(header_value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def fetch_latest_verification_code(timeout_seconds=60, poll_interval=3, since_time=None):
    """
    通过 POP3 收取最新邮件中的验证码。
    since_time: Unix 时间戳，只接受该时间之后的邮件（防止读取历史验证码）
    返回 (code: str | None, error: str | None)
    """
    deadline = time.time() + timeout_seconds
    last_check_count = None

    while time.time() < deadline:
        try:
            if POP3_USE_SSL:
                conn = poplib.POP3_SSL(POP3_HOST, POP3_PORT, timeout=10)
            else:
                conn = poplib.POP3(POP3_HOST, POP3_PORT, timeout=10)

            conn.user(POP3_USERNAME)
            conn.pass_(POP3_PASSWORD)

            msg_count, _ = conn.stat()
            print(f"[POP3] 邮箱共 {msg_count} 封邮件")

            if msg_count == 0:
                conn.quit()
                time.sleep(poll_interval)
                continue

            # 增量检测：无新邮件则等待
            if last_check_count is not None and msg_count == last_check_count:
                conn.quit()
                time.sleep(poll_interval)
                continue

            last_check_count = msg_count

            # 取最后一封
            resp, lines, octets = conn.retr(msg_count)
            raw_email = b"\r\n".join(lines)
            conn.quit()

            msg = email.message_from_bytes(raw_email)
            subject = decode_mime_header(msg["Subject"] or "")
            sender = decode_mime_header(msg["From"] or "")
            date = msg.get("Date", "")

            print(f"[POP3] 最新邮件: 发件人={sender}, 主题={subject}, 时间={date}")

            # 时间过滤：跳过登录触发前收到的邮件，防止读取历史验证码
            if since_time is not None and date:
                try:
                    email_dt = parsedate_to_datetime(date)
                    if email_dt.timestamp() < since_time:
                        print(f"[POP3] ⏭ 邮件时间早于登录触发时间，等待新邮件...")
                        time.sleep(poll_interval)
                        continue
                except Exception:
                    pass  # 日期解析失败不阻塞

            # 提取正文（优先纯文本，避免 HTML 噪声干扰）
            text_parts = []
            html_parts = []
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type not in ("text/plain", "text/html"):
                        continue
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        decoded = payload.decode(charset, errors="replace")
                        if content_type == "text/plain":
                            text_parts.append(decoded)
                        else:
                            html_parts.append(decoded)
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace"))

            # 纯文本优先（噪声少），再拼接 HTML
            plain_body = "\n".join(text_parts)
            full_body = plain_body + "\n" + "\n".join(html_parts)

            # 从正文中提取验证码
            # 策略：优先匹配数字验证码（站点要求6位数字），字母数字作为兜底
            digit_patterns = [
                # 紧邻 "验证码" 的 6 位数字（最精确）
                (r"验证码[：:\s]*(?:是|为)?[：:\s]*(\d{6})", "6位数字紧邻验证码"),
                # "code:" 后 6 位数字
                (r"(?:code|Code|CODE)[：:\s]*(\d{6})", "6位数字紧邻code"),
                # 正文中任意 6 位数字（大概率是验证码）
                (r"(?<!\d)(\d{6})(?!\d)", "独立6位数字"),
            ]
            alphanum_patterns = [
                # "验证码" 后 4-8 位字母数字（兜底）
                (r"验证码[：:\s]*(?:是|为)?[：:\s]*([A-Za-z0-9]{4,8})", "4-8位字母数字紧邻验证码"),
                # "code:" 后 4-8 位字母数字
                (r"(?:code|Code|CODE)[：:\s]*([A-Za-z0-9]{4,8})", "4-8位字母数字紧邻code"),
            ]

            def try_extract(body: str, label: str) -> str | None:
                """在给定文本中尝试提取验证码，优先数字模式"""
                for pattern, desc in digit_patterns + alphanum_patterns:
                    match = re.search(pattern, body)
                    if match:
                        code = match.group(1)
                        # 打印匹配上下文便于调试
                        start = max(0, match.start() - 20)
                        end = min(len(body), match.end() + 20)
                        ctx = body[start:end].replace("\n", " ")
                        print(f"[POP3] ✅ [{label}] {desc}: {code} (上下文: ...{ctx}...)")
                        return code
                return None

            # 先搜纯文本，再搜全文
            code = try_extract(plain_body, "纯文本")
            if code is None:
                code = try_extract(full_body, "全文")
            if code is not None:
                return code, None

            # 降级：打印正文前 500 字符供人工判断
            print(f"[POP3] ⚠️ 未能自动提取验证码，纯文本前500字符:")
            print(plain_body[:500])
            if html_parts:
                print(f"[POP3] HTML 前300字符:")
                print(html_parts[0][:300])

        except Exception as e:
            print(f"[POP3] 连接错误: {e}")
            time.sleep(poll_interval)
            continue

        time.sleep(poll_interval)

    return None, f"超时 {timeout_seconds}s 未获取到验证码"


# ── CloakBrowser 主流程 ─────────────────────────────

def main():
    print("=" * 60)
    print("CordCloud Auto Login + Daily Check-in")
    print(f"CloakBrowser + POP3 ({POP3_HOST}:{POP3_PORT})")
    print("=" * 60)

    # 校验配置
    if not CORDCLOUD_EMAIL or not CORDCLOUD_PASSWORD:
        print("[ERROR] 请先配置 .env 文件中的 CORDCLOUD_EMAIL 和 CORDCLOUD_PASSWORD")
        return

    # 启动 CloakBrowser（Playwright 兼容）
    print("\n[Browser] 启动 CloakBrowser...")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    if USE_PERSISTENT:
        context = launch_persistent_context(
            PROFILE_DIR,
            headless=HEADLESS,
            viewport={"width": 1280, "height": 800},
            humanize=True,
        )
        # launch_persistent_context returns BrowserContext (Playwright-compatible)
        page = context.new_page()
        real_browser = None  # persistent context manages its own browser
    else:
        real_browser = launch(headless=HEADLESS, humanize=True)
        context = real_browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

    results = []  # 收集各步骤结果用于邮件汇总
    checkin_screenshot = None  # 签到页面截图路径

    try:
        # ── Step 1: 检查是否已登录 ──
        print("\n[Step 1] 检查登录状态...")
        page.goto(USER_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        save_page_state(page, "step1_check_login")

        # 如果跳转到 /user 则已登录
        current_url = page.url
        if "/user" in current_url or "/user/" in current_url:
            print("[Step 1] ✅ 已有有效会话，跳过登录")
            results.append("[Step 1] 已有有效会话，跳过登录")
        else:
            # ── Step 2: 登录 ──
            print("\n[Step 2] 开始登录...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            save_page_state(page, "step2_login_page")

            # 等待表单就绪，避免页面 JS 尚未初始化完成导致 fill 竞态
            email_input = page.locator("#email")
            passwd_input = page.locator("#passwd")
            email_input.wait_for(state="visible", timeout=10000)
            passwd_input.wait_for(state="visible", timeout=10000)

            # 先点击聚焦，确保页面 JS 的 autofocus/select-all 已完成
            email_input.click()
            page.wait_for_timeout(500)
            email_input.fill(CORDCLOUD_EMAIL)

            passwd_input.click()
            page.wait_for_timeout(500)
            passwd_input.fill(CORDCLOUD_PASSWORD)

            # 验证填入的值是否正确（防止全选/清空导致填入失败）
            filled_email = email_input.input_value()
            if filled_email != CORDCLOUD_EMAIL:
                print(f"[Step 2] ⚠️ 邮箱填入不匹配 (期望={CORDCLOUD_EMAIL}, 实际={filled_email})，重试...")
                email_input.click()
                page.wait_for_timeout(300)
                email_input.fill(CORDCLOUD_EMAIL)
                filled_email = email_input.input_value()
                if filled_email != CORDCLOUD_EMAIL:
                    print(f"[Step 2] ❌ 邮箱重试仍失败: {filled_email}")
                else:
                    print(f"[Step 2] ✅ 邮箱重试成功")

            print(f"[Step 2] 已填写: {CORDCLOUD_EMAIL}")
            results.append(f"[Step 2] 填写登录表单: {CORDCLOUD_EMAIL}")

            # 点击登录按钮，记录触发时间用于过滤历史邮件
            login_click_time = time.time()
            page.click("#login")
            print(f"[Step 2] 已点击登录 (触发时间: {time.strftime('%H:%M:%S', time.localtime(login_click_time))})，等待响应...")
            time.sleep(3)

            current_url = page.url
            print(f"[Step 2] 当前 URL: {current_url}")
            save_page_state(page, "step3_after_login_click")

            # ── 检测 2FA（URL + 输入框双重确认） ──
            in_2fa = ("/2fa" in current_url or "/auth/login/2fa" in current_url)
            if not in_2fa:
                # 降级：检查 #code 输入框是否存在
                try:
                    in_2fa = page.locator("#code").is_visible()
                except Exception:
                    pass

            if in_2fa:
                print(f"[Step 2] 🔐 检测到 2FA 页面")
                print("[Step 2] 正在从 POP3 收取验证码...")

                code, error = fetch_latest_verification_code(timeout_seconds=90, since_time=login_click_time)
                if error or not code:
                    print(f"[Step 2] ❌ {error}")
                    return

                # 填写验证码到 #code 输入框 (input#code, maxlength=6, pattern=[0-9]*)
                try:
                    page.locator("#code").fill(code)
                    print(f"[Step 2] 已填写验证码: {code}")
                except Exception:
                    print(f"[Step 2] ⚠️ 未找到 #code 输入框")
                    return

                # 提交 2FA：按钮 #btn-verify (type=submit, text="确认验证")
                page.locator("#btn-verify").click()
                print("[Step 2] 已提交验证，等待响应...")

                # 等待结果：成功则跳转到 /user，失败则弹窗 #msg
                # JS 逻辑: ret===1 → #msg 弹窗 → 500ms 后 location.href='/user'
                #          ret!==1 → #msg 弹窗显示错误，留在当前页
                try:
                    page.wait_for_url("**/user**", timeout=10000)
                    print("[Step 2] ✅ 2FA 验证成功，已跳转到用户页面")
                    results.append("[Step 2] 2FA 验证成功")
                except Exception:
                    # 未跳转，检查 #msg 弹窗错误信息
                    try:
                        msg_el = page.locator("#msg")
                        if msg_el.is_visible():
                            error_text = (msg_el.text_content() or "").strip()
                            print(f"[Step 2] ❌ 2FA 验证失败: {error_text}")
                            results.append(f"[Step 2] 2FA 验证失败: {error_text}")
                            return
                    except Exception:
                        pass
                    print("[Step 2] ⚠️ 2FA 提交后未跳转，状态未知")
                    # 不 return，继续检查当前 URL

                save_page_state(page, "step4_after_2fa")
            else:
                print("[Step 2] 未检测到 2FA，等待登录跳转...")
                time.sleep(3)

            current_url = page.url

            # 二次确认：检查 #msg 弹窗是否有遗留错误
            try:
                msg_el = page.locator("#msg")
                if msg_el.is_visible():
                    error_msg = (msg_el.text_content() or "").strip()
                    if error_msg:
                        print(f"[Step 2] ❌ 登录错误: {error_msg}")
                        return
            except Exception:
                pass

            if "/user" in current_url or "/user/" in current_url:
                print("[Step 2] ✅ 登录成功！")
                results.append("[Step 2] 登录成功")
            else:
                print(f"[Step 2] ⚠️ 登录后 URL: {current_url}，继续尝试...")
                results.append(f"[Step 2] 登录后未跳转到 /user，当前: {current_url}")

        # ── Step 3: 每日签到 ──
        print("\n[Step 3] 查找每日签到...")
        page.goto(USER_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        save_page_state(page, "step5_user_checkin")

        # 签到按钮位于 #checkin-btn 容器内
        # 未签到: <button id="checkin">签到</button>
        # 已签到: <button disabled>已签到</button> (无 id)
        try:
            checkin_btn = page.locator("#checkin-btn button")
            if not checkin_btn.is_visible():
                print("[Step 3] ⚠️ 未找到签到按钮，页面结构可能有变")
                results.append("[Step 3] 未找到签到按钮")
            else:
                is_disabled = checkin_btn.is_disabled()
                btn_text = (checkin_btn.text_content() or "").strip()
                if is_disabled or "已签到" in btn_text:
                    # 提取上次签到时间（<p>上次：2026-05-12 15:09:48</p>）
                    try:
                        last_el = page.locator("p:has-text('上次')").first
                        if last_el.is_visible():
                            last_time_text = (last_el.text_content() or "").strip()
                            print(f"[Step 3] 今日已签到，{last_time_text}")
                            results.append(f"[Step 3] 今日已签到，{last_time_text}")
                        else:
                            print(f"[Step 3] 今日已签到")
                            results.append("[Step 3] 今日已签到")
                    except Exception:
                        print(f"[Step 3] 今日已签到")
                        results.append("[Step 3] 今日已签到")
                else:
                    print(f"[Step 3] 点击签到按钮: '{btn_text}'")
                    checkin_btn.click()
                    time.sleep(2)

                    # 检查签到结果: #checkin-msg 内联消息
                    checkin_msg = ""
                    try:
                        msg_el = page.locator("#checkin-msg")
                        if msg_el.is_visible():
                            checkin_msg = (msg_el.text_content() or "").strip()
                            if checkin_msg:
                                print(f"[Step 3] 签到结果: {checkin_msg}")
                    except Exception:
                        pass
                    results.append(f"[Step 3] 签到完成: {checkin_msg or '已执行'}")

            print("[Step 3] ✅ 签到操作完成")
            checkin_screenshot = save_page_state(page, "step6_after_checkin")
        except Exception as e:
            print(f"[Step 3] ⚠️ 签到操作异常: {e}")
            checkin_screenshot = None

        # ── 发送结果邮件 ──
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        email_subject = f"CordCloud 签到结果 - {now}"
        email_body = "\n".join(results)
        send_result_email(email_subject, email_body, checkin_screenshot)

        print("\n" + "=" * 60)
        print("✅ 任务完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        results.append(f"[ERROR] {e}")

    finally:
        print("\n[Browser] 保持浏览器打开（5秒后自动关闭）...")
        time.sleep(5)
        if USE_PERSISTENT:
            context.close()
        else:
            if real_browser:
                real_browser.close()


if __name__ == "__main__":
    main()
