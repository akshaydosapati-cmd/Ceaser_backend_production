import os

import resend


def send_test_email(to_email: str):
    api_key = os.getenv("RESEND_API_KEY")
    email_from = os.getenv("EMAIL_FROM")

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")
    if not email_from:
        raise RuntimeError("EMAIL_FROM is not configured")

    resend.api_key = api_key

    html_content = """
    <div style="font-family: Arial, Helvetica, sans-serif; background-color: #f6f8fb; padding: 24px; margin: 0;">
      <div style="max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 8px 24px rgba(8, 11, 24, 0.08);">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #2563eb 100%); padding: 32px 24px; text-align: center; color: #ffffff;">
          <h1 style="margin: 0 0 8px; font-size: 28px; line-height: 1.2;">Welcome to CEASER</h1>
          <p style="margin: 0; font-size: 16px; opacity: 0.95;">Your launch list membership is confirmed.</p>
        </div>
        <div style="padding: 32px 24px; color: #111827;">
          <p style="margin: 0 0 16px; font-size: 16px; line-height: 1.7;">Hi,</p>
          <p style="margin: 0 0 16px; font-size: 16px; line-height: 1.7;">Thank you for joining the CEASER Launch List.</p>
          <p style="margin: 0 0 16px; font-size: 16px; line-height: 1.7;">You're now one of the earliest people who will receive access when CEASER officially launches.</p>
          <p style="margin: 0 0 16px; font-size: 16px; line-height: 1.7;">You'll receive:</p>
          <ul style="margin: 0 0 24px 20px; padding: 0; font-size: 16px; line-height: 1.7; color: #374151;">
            <li>Launch announcements</li>
            <li>Product updates</li>
            <li>Early access opportunities</li>
            <li>Feature releases</li>
          </ul>
          <div style="text-align: center; margin: 24px 0 8px;">
            <a href="https://heyceaser.in" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 999px; font-weight: 600;">Visit CEASER</a>
          </div>
        </div>
        <div style="background: #f8fafc; padding: 24px; text-align: center; color: #64748b; font-size: 13px; line-height: 1.6; border-top: 1px solid #e5e7eb;">
          <p style="margin: 0 0 6px;">Built with ❤️ in India</p>
          <p style="margin: 0;">© 2026 CEASER</p>
        </div>
      </div>
    </div>
    """

    return resend.Emails.send(
        {
            "from": email_from,
            "to": [to_email],
            "subject": "🚀 Welcome to CEASER",
            "html": html_content,
            "text": "Thank you for joining the CEASER Launch List. Visit https://heyceaser.in to learn more.",
        }
    )
