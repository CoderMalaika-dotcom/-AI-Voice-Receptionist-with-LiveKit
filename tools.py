import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from livekit.agents import function_tool, RunContext

logger = logging.getLogger("CrincleCupkakes")

# =========================
# Email Tool
# =========================
@function_tool
async def send_email(
    context: RunContext,
    to_email: str,
    subject: str,
    body: str,
) -> str:
    """
    Send an email to a customer or team member.

    Use this tool when:
    - A customer wants to receive the menu, pricing, or custom order details
    - An order has been confirmed and you need to send a confirmation
    - You want to follow up with a customer

    Args:
        to_email: The recipient's email address (e.g. customer@gmail.com)
        subject: The email subject line
        body: The full email body content (plain text)

    Returns:
        A confirmation message indicating success or failure
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    # Validate config
    if not smtp_user or not smtp_password:
        logger.error("❌ SMTP credentials not configured in .env.local")
        return "Sorry, email service is not configured. Please contact us at team@crinclecupkakes.com."

    # Validate recipient
    if not to_email or "@" not in to_email:
        logger.error(f"❌ Invalid email address: {to_email}")
        return "That email address doesn't look right. Could you double-check it for me?"

    try:
        # Build the email
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Crincle Cupkakes <{from_email}>"
        msg["To"] = to_email

        # Plain text part
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)

        # HTML part — wraps the plain body in a simple branded template
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: auto; padding: 20px;">
            <div style="background-color: #f9e4ef; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
              <h2 style="color: #c0306a; margin: 0;">🧁 Crincle Cupkakes</h2>
              <p style="margin: 4px 0; font-size: 13px; color: #888;">123 Main Street, Karachi</p>
            </div>
            <div style="line-height: 1.7; white-space: pre-line;">{body}</div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;" />
            <p style="font-size: 12px; color: #aaa; text-align: center;">
              Crincle Cupkakes · Karachi · team@crinclecupkakes.com
            </p>
          </body>
        </html>
        """
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        # Send via SMTP
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_email, msg.as_string())

        logger.info(f"✅ Email sent to {to_email} | Subject: {subject}")
        return f"Email sent successfully to {to_email}!"

    except smtplib.SMTPAuthenticationError:
        logger.error("❌ SMTP authentication failed — check SMTP_USER and SMTP_PASSWORD")
        return "I wasn't able to send the email due to a configuration issue. Please reach out to us at team@crinclecupkakes.com."

    except smtplib.SMTPException as e:
        logger.error(f"❌ SMTP error: {e}")
        return "There was a problem sending the email. Please try again or contact us directly."

    except Exception as e:
        logger.error(f"❌ Unexpected email error: {e}")
        return "Something went wrong while sending the email. I apologize for the inconvenience!"