import re
import time

from cloakbrowser import launch, launch_persistent_context

from .config import Settings
from .mail import fetch_latest_verification_code, mask_code, send_result_email


def normalize_numeric_code(code: str) -> str:
    """Return only digits from a verification code."""
    return re.sub(r"\D", "", code)


def fill_verification_code(page, code: str) -> bool:
    """Fill the 2FA code and verify the page sees exactly 6 digits."""
    numeric_code = normalize_numeric_code(code)
    if len(numeric_code) != 6:
        print(f"[Step 2] ❌ 验证码不是6位数字: {mask_code(code)}")
        return False

    code_input = page.locator("#code")
    code_input.wait_for(state="visible", timeout=10000)
    code_input.click()
    code_input.fill("")
    code_input.press_sequentially(numeric_code, delay=80)
    code_input.evaluate(
        """el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )

    actual_value = code_input.input_value().strip()
    if actual_value != numeric_code:
        code_input.evaluate(
            """(el, value) => {
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            numeric_code,
        )
        actual_value = code_input.input_value().strip()

    if actual_value != numeric_code:
        print(f"[Step 2] ❌ 验证码填入后页面读取不一致: {len(actual_value)} 位")
        return False

    print(f"[Step 2] 已填写验证码: {mask_code(numeric_code)}")
    return True


def text_indicates_checkin_success(text: str) -> bool:
    """Return whether page text looks like a completed traffic check-in."""
    normalized = text.strip()
    if not normalized:
        return False
    if "已签到" in normalized:
        return True
    has_traffic_amount = re.search(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)", normalized, re.IGNORECASE)
    return bool(has_traffic_amount and ("获得" in normalized or "流量" in normalized))


def save_page_state(settings: Settings, page, step_name: str) -> str | None:
    """Save current page HTML and screenshot for debugging."""
    if not settings.save_html:
        return None

    settings.debug_html_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%H%M%S")
    html_path = settings.debug_html_dir / f"{timestamp}_{step_name}.html"
    png_path = settings.debug_html_dir / f"{timestamp}_{step_name}.png"

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


def run_checkin(settings: Settings) -> bool:
    print("=" * 60)
    print("CordCloud Auto Login + Daily Check-in")
    print(f"CloakBrowser + POP3 ({settings.pop3_host}:{settings.pop3_port})")
    print("=" * 60)

    if not settings.cordcloud_email or not settings.cordcloud_password:
        print("[ERROR] 请先配置 .env 文件中的 CORDCLOUD_EMAIL 和 CORDCLOUD_PASSWORD")
        return False

    print("\n[Browser] 启动 CloakBrowser...")
    settings.persistent_profile_dir.mkdir(parents=True, exist_ok=True)

    if settings.use_persistent_context:
        context = launch_persistent_context(
            settings.persistent_profile_dir,
            headless=settings.headless,
            viewport={"width": 1280, "height": 800},
            humanize=True,
        )
        page = context.new_page()
        real_browser = None
    else:
        real_browser = launch(headless=settings.headless, humanize=True)
        context = real_browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

    results = []
    checkin_screenshot = None
    checkin_success = False

    try:
        print("\n[Step 1] 检查登录状态...")
        page.goto(settings.user_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        save_page_state(settings, page, "step1_check_login")

        current_url = page.url
        if "/user" in current_url or "/user/" in current_url:
            print("[Step 1] ✅ 已有有效会话，跳过登录")
            results.append("[Step 1] 已有有效会话，跳过登录")
        else:
            print("\n[Step 2] 开始登录...")
            page.goto(settings.login_url, wait_until="networkidle", timeout=30000)
            save_page_state(settings, page, "step2_login_page")

            email_input = page.locator("#email")
            passwd_input = page.locator("#passwd")
            email_input.wait_for(state="visible", timeout=10000)
            passwd_input.wait_for(state="visible", timeout=10000)

            email_input.click()
            page.wait_for_timeout(500)
            email_input.fill(settings.cordcloud_email)

            passwd_input.click()
            page.wait_for_timeout(500)
            passwd_input.fill(settings.cordcloud_password)

            filled_email = email_input.input_value()
            if filled_email != settings.cordcloud_email:
                print(f"[Step 2] ⚠️ 邮箱填入不匹配 (期望={settings.cordcloud_email}, 实际={filled_email})，重试...")
                email_input.click()
                page.wait_for_timeout(300)
                email_input.fill(settings.cordcloud_email)
                filled_email = email_input.input_value()
                if filled_email != settings.cordcloud_email:
                    print(f"[Step 2] ❌ 邮箱重试仍失败: {filled_email}")
                else:
                    print("[Step 2] ✅ 邮箱重试成功")

            print(f"[Step 2] 已填写: {settings.cordcloud_email}")
            results.append(f"[Step 2] 填写登录表单: {settings.cordcloud_email}")

            login_click_time = time.time()
            page.click("#login")
            print(f"[Step 2] 已点击登录 (触发时间: {time.strftime('%H:%M:%S', time.localtime(login_click_time))})，等待响应...")
            time.sleep(3)

            current_url = page.url
            print(f"[Step 2] 当前 URL: {current_url}")
            save_page_state(settings, page, "step3_after_login_click")

            in_2fa = "/2fa" in current_url or "/auth/login/2fa" in current_url
            if not in_2fa:
                try:
                    in_2fa = page.locator("#code").is_visible()
                except Exception:
                    pass

            if in_2fa:
                print("[Step 2] 🔐 检测到 2FA 页面")
                print("[Step 2] 正在从 POP3 收取验证码...")

                code, error = fetch_latest_verification_code(settings, timeout_seconds=90, since_time=login_click_time)
                if error or not code:
                    print(f"[Step 2] ❌ {error}")
                    return False

                try:
                    if not fill_verification_code(page, code):
                        save_page_state(settings, page, "step4_code_fill_failed")
                        return False
                except Exception as e:
                    print(f"[Step 2] ⚠️ 填写验证码异常: {e}")
                    print("[Step 2] ⚠️ 未找到 #code 输入框")
                    return False

                page.locator("#btn-verify").click()
                print("[Step 2] 已提交验证，等待响应...")

                try:
                    page.wait_for_url("**/user**", timeout=10000)
                    print("[Step 2] ✅ 2FA 验证成功，已跳转到用户页面")
                    results.append("[Step 2] 2FA 验证成功")
                except Exception:
                    try:
                        msg_el = page.locator("#msg")
                        if msg_el.is_visible():
                            error_text = (msg_el.text_content() or "").strip()
                            print(f"[Step 2] ❌ 2FA 验证失败: {error_text}")
                            results.append(f"[Step 2] 2FA 验证失败: {error_text}")
                            return False
                    except Exception:
                        pass
                    print("[Step 2] ⚠️ 2FA 提交后未跳转，状态未知")

                save_page_state(settings, page, "step4_after_2fa")
            else:
                print("[Step 2] 未检测到 2FA，等待登录跳转...")
                time.sleep(3)

            current_url = page.url

            try:
                msg_el = page.locator("#msg")
                if msg_el.is_visible():
                    error_msg = (msg_el.text_content() or "").strip()
                    if error_msg:
                        print(f"[Step 2] ❌ 登录错误: {error_msg}")
                        return False
            except Exception:
                pass

            if "/user" in current_url or "/user/" in current_url:
                print("[Step 2] ✅ 登录成功！")
                results.append("[Step 2] 登录成功")
            else:
                print(f"[Step 2] ⚠️ 登录后 URL: {current_url}，继续尝试...")
                results.append(f"[Step 2] 登录后未跳转到 /user，当前: {current_url}")

        print("\n[Step 3] 查找每日签到...")
        page.goto(settings.user_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        save_page_state(settings, page, "step5_user_checkin")

        try:
            checkin_btn = page.locator("#checkin-btn button")
            if not checkin_btn.is_visible():
                print("[Step 3] ⚠️ 未找到签到按钮，页面结构可能有变")
                results.append("[Step 3] 未找到签到按钮")
            else:
                is_disabled = checkin_btn.is_disabled()
                btn_text = (checkin_btn.text_content() or "").strip()
                if is_disabled or "已签到" in btn_text:
                    try:
                        last_el = page.locator("p:has-text('上次')").first
                        if last_el.is_visible():
                            last_time_text = (last_el.text_content() or "").strip()
                            print(f"[Step 3] 今日已签到，{last_time_text}")
                            results.append(f"[Step 3] 今日已签到，{last_time_text}")
                        else:
                            print("[Step 3] 今日已签到")
                            results.append("[Step 3] 今日已签到")
                    except Exception:
                        print("[Step 3] 今日已签到")
                        results.append("[Step 3] 今日已签到")
                    checkin_success = True
                else:
                    print(f"[Step 3] 点击签到按钮: '{btn_text}'")
                    checkin_btn.click()
                    time.sleep(2)

                    checkin_msg = ""
                    try:
                        msg_el = page.locator("#checkin-msg")
                        if msg_el.is_visible():
                            checkin_msg = (msg_el.text_content() or "").strip()
                            if checkin_msg:
                                print(f"[Step 3] 签到结果: {checkin_msg}")
                    except Exception:
                        pass

                    post_btn_text = ""
                    post_btn_done = False
                    try:
                        post_btn_text = (checkin_btn.text_content() or "").strip()
                        post_btn_done = checkin_btn.is_disabled() or "已签到" in post_btn_text
                    except Exception:
                        pass

                    checkin_success = post_btn_done or text_indicates_checkin_success(checkin_msg)
                    if checkin_success:
                        results.append(f"[Step 3] 签到成功: {checkin_msg or post_btn_text or '已签到'}")
                    else:
                        print("[Step 3] ⚠️ 签到后未确认获得流量或已签到状态")
                        results.append(f"[Step 3] 签到结果未确认: {checkin_msg or post_btn_text or '无页面反馈'}")

            if checkin_success:
                print("[Step 3] ✅ 签到操作完成")
            else:
                print("[Step 3] ❌ 签到未成功确认")
            checkin_screenshot = save_page_state(settings, page, "step6_after_checkin")
        except Exception as e:
            print(f"[Step 3] ⚠️ 签到操作异常: {e}")
            checkin_screenshot = None

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        email_subject = f"CordCloud 签到结果 - {now}"
        email_body = "\n".join(results)
        send_result_email(settings, email_subject, email_body, checkin_screenshot)

        print("\n" + "=" * 60)
        if checkin_success:
            print("✅ 任务完成")
        else:
            print("❌ 任务未成功完成")
        print("=" * 60)
        return checkin_success

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        results.append(f"[ERROR] {e}")
        return False

    finally:
        print("\n[Browser] 保持浏览器打开（5秒后自动关闭）...")
        time.sleep(5)
        if settings.use_persistent_context:
            context.close()
        elif real_browser:
            real_browser.close()
