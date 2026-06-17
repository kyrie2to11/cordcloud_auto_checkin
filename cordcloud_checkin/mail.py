import email
import poplib
import re
import smtplib
import time
from email.header import decode_header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import Message
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

from .config import Settings


def mask_code(code: str) -> str:
    """Mask a verification code, keeping only the first and last character."""
    if len(code) <= 2:
        return "*" * len(code)
    return code[0] + "*" * (len(code) - 2) + code[-1]


def decode_mime_header(header_value: str | None) -> str:
    """Decode a MIME-encoded email header."""
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


def extract_message_bodies(msg: Message) -> tuple[str, str]:
    """Return plain text body and combined text+HTML body for an email message."""
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

    plain_body = "\n".join(text_parts)
    full_body = plain_body + "\n" + "\n".join(html_parts)
    return plain_body, full_body


def extract_verification_code(body: str) -> tuple[str | None, str | None]:
    """Extract a verification code from message text."""
    digit_patterns = [
        (r"验证码[：:\s]*(?:是|为)?[：:\s]*(\d{6})", "6位数字紧邻验证码"),
        (r"(?:code|Code|CODE)[：:\s]*(\d{6})", "6位数字紧邻code"),
        (r"(?<!\d)(\d{6})(?!\d)", "独立6位数字"),
    ]
    alphanum_patterns = [
        (r"验证码[：:\s]*(?:是|为)?[：:\s]*([A-Za-z0-9]{4,8})", "4-8位字母数字紧邻验证码"),
        (r"(?:code|Code|CODE)[：:\s]*([A-Za-z0-9]{4,8})", "4-8位字母数字紧邻code"),
    ]

    for pattern, desc in digit_patterns + alphanum_patterns:
        match = re.search(pattern, body)
        if match:
            return match.group(1), desc
    return None, None


def extract_code_from_message(msg: Message) -> tuple[str | None, str | None, str, str | None]:
    """Extract a verification code from an email, preferring the plain text body."""
    plain_body, full_body = extract_message_bodies(msg)

    code, desc = extract_verification_code(plain_body)
    if code:
        return code, desc, "纯文本", plain_body

    code, desc = extract_verification_code(full_body)
    if code:
        return code, desc, "全文", full_body

    return None, None, "", plain_body


def message_is_before(msg: Message, since_time: float | None) -> bool:
    if since_time is None:
        return False

    date = msg.get("Date", "")
    if not date:
        return False

    try:
        email_dt = parsedate_to_datetime(date)
        return email_dt.timestamp() < since_time
    except Exception:
        return False


def send_result_email(settings: Settings, subject: str, body: str, image_path: str | None = None) -> None:
    """Send the check-in result email to the CordCloud account address."""
    if not settings.smtp_password:
        print("[SMTP] 未配置 SMTP_PASSWORD，跳过邮件发送")
        return

    try:
        if image_path:
            msg = MIMEMultipart("related")
            msg["From"] = settings.smtp_username
            msg["To"] = settings.cordcloud_email
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

            msg.attach(MIMEText(body, "plain", "utf-8"))

            with open(image_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="png")
                img.add_header("Content-Disposition", "attachment", filename=Path(image_path).name)
                msg.attach(img)
        else:
            msg = MIMEText(body, "plain", "utf-8")
            msg["From"] = settings.smtp_username
            msg["To"] = settings.cordcloud_email
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

        if settings.smtp_use_ssl:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            server.starttls()

        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_username, [settings.cordcloud_email], msg.as_string())
        server.quit()
        print(f"[SMTP] ✅ 结果邮件已发送至 {settings.cordcloud_email}")
    except Exception as e:
        print(f"[SMTP] ❌ 邮件发送失败: {e}")


def fetch_latest_verification_code(
    settings: Settings,
    timeout_seconds: int = 60,
    poll_interval: int = 3,
    since_time: float | None = None,
) -> tuple[str | None, str | None]:
    """
    Fetch a verification code from recent POP3 messages.

    since_time filters out messages received before the login was triggered.
    """
    deadline = time.time() + timeout_seconds
    last_check_count = None

    while time.time() < deadline:
        try:
            if settings.pop3_use_ssl:
                conn = poplib.POP3_SSL(settings.pop3_host, settings.pop3_port, timeout=10)
            else:
                conn = poplib.POP3(settings.pop3_host, settings.pop3_port, timeout=10)

            conn.user(settings.pop3_username)
            conn.pass_(settings.pop3_password)

            msg_count, _ = conn.stat()
            print(f"[POP3] 邮箱共 {msg_count} 封邮件")

            if msg_count == 0:
                conn.quit()
                time.sleep(poll_interval)
                continue

            if last_check_count is not None and msg_count == last_check_count:
                conn.quit()
                time.sleep(poll_interval)
                continue

            last_check_count = msg_count
            first_msg = max(1, msg_count - settings.pop3_scan_limit + 1)
            message_numbers = range(msg_count, first_msg - 1, -1)
            fallback_plain_body = ""

            for msg_num in message_numbers:
                resp, lines, octets = conn.retr(msg_num)
                raw_email = b"\r\n".join(lines)
                msg = email.message_from_bytes(raw_email)
                subject = decode_mime_header(msg["Subject"] or "")
                sender = decode_mime_header(msg["From"] or "")
                date = msg.get("Date", "")

                print(f"[POP3] 检查邮件 #{msg_num}: 发件人={sender}, 主题={subject}, 时间={date}")

                if message_is_before(msg, since_time):
                    print("[POP3] ⏭ 邮件时间早于登录触发时间，跳过")
                    continue

                code, desc, source, body = extract_code_from_message(msg)
                fallback_plain_body = fallback_plain_body or body
                if code:
                    print(f"[POP3] ✅ [{source}] {desc}: {mask_code(code)}")
                    conn.quit()
                    return code, None

            conn.quit()
            print("[POP3] ⚠️ 最近邮件中未能自动提取验证码，纯文本前500字符:")
            print(fallback_plain_body[:500])

        except Exception as e:
            print(f"[POP3] 连接错误: {e}")
            time.sleep(poll_interval)
            continue

        time.sleep(poll_interval)

    return None, f"超时 {timeout_seconds}s 未获取到验证码"
