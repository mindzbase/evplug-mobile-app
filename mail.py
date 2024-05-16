from email import encoders
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
import os
from pathlib import Path
import aiosmtplib
from config import config


async def send_mail(receiver, subject, content):
    message = EmailMessage()
    message["From"] = config["SENDER_EMAIL"]
    message["To"] = receiver
    message["Subject"] = subject
    message.set_content(content)

    await aiosmtplib.send(
        message,
        hostname=config["EMAIL_HOSTNAME"],
        port=config["EMAIL_PORT"],
        username=config["SENDER_EMAIL"],
        password=config["EMAIL_PASSWORD"],
        use_tls=True,
    )


async def send_plain_invoice_email(invoice_details, tenant_detail, receiver_email):
    from utils import LOGGER

    try:
        # async def send_invoice_html_email(invoice_details, org_details, receiver_email):
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from routes.ocpp_routes import generate_invoice

        smtp_server = config["EMAIL_HOSTNAME"]
        port = 587
        username = config["SENDER_EMAIL"]
        password = config["EMAIL_PASSWORD"]
        from_addr = config["SENDER_EMAIL"]
        to_addr = receiver_email
        subject = (
            f"EV charging Invoice for session {invoice_details.get('session_id')}."
        )
        message = MIMEMultipart("alternative")
        message["From"] = from_addr
        message["To"] = to_addr
        message["Subject"] = subject

        plain_text_message = MIMEText(
            f"""
    Dear {invoice_details.get('name')},

    Thank you for charging with us today. We hope that you had a positive experience.
    Please find your charging session invoice attached to this email.

    If you have any questions about your invoice, please do not hesitate to contact us.
    Thank you again for choosing our charging station. We look forward to seeing you again soon.

        {org_details.get('org_name')}
        """,
            "plain",
            "utf-8",
        )

        message.attach(plain_text_message)
        pdf_content = await generate_invoice(
            session_id=invoice_details.get("session_id"),
            org_id=org_details.get("org_id"),
        )
        if pdf_content:
            pdf_part = MIMEApplication(pdf_content, "pdf")
            pdf_part.add_header(
                "Content-Disposition", "attachment; filename=invoice.pdf"
            )
            message.attach(pdf_part)
        else:
            LOGGER.info("skipped pdf generation.")
        await aiosmtplib.send(
            message,
            hostname=smtp_server,
            port=port,
            password=password,
            username=username,
        )
        return
    except Exception as e:
        LOGGER.error(e)


# async def send_invoice_html_email(invoice_details, org_details, receiver_email):
#     from email.mime.multipart import MIMEMultipart
#     from email.mime.text import MIMEText
#     from utils import get_email_html
#     from routes.ocpp_routes import generate_invoice

#     smtp_server = config["EMAIL_HOSTNAME"]
#     port = 587
#     username = config["SENDER_EMAIL"]
#     password = config["EMAIL_PASSWORD"]
#     from_addr = config["SENDER_EMAIL"]
#     to_addr = receiver_email
#     subject = f"EV charging Invoice for session {invoice_details.get('session_id')}."
#     message = MIMEMultipart("alternative")
#     message["From"] = from_addr
#     message["To"] = to_addr
#     message["Subject"] = subject

#     plain_text_message = MIMEText("Sent via aiosmtplib", "plain", "utf-8")
#     html_content = MIMEText(
#         get_email_html(
#             invoice_details=invoice_details, organisation_details=org_details
#         ),
#         "html",
#         "utf-8",
#     )

#     pdf_content = await generate_invoice(
#         session_id=invoice_details.get("session_id"),
#         org_id=org_details.get("org_id"),
#     )
#     message.attach(plain_text_message)
#     message.attach(html_content)
#     if pdf_content:
#         pdf_part = MIMEApplication(pdf_content, "pdf")
#         pdf_part.add_header("Content-Disposition", "attachment; filename=invoice.pdf")
#         message.attach(pdf_part)
#     await aiosmtplib.send(
#         message, hostname=smtp_server, port=port, password=password, username=username
#     )
#     return


async def send_verification_mail(
    receiver_email, verification_url, valid_minute, organisation_details
):
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from html_templates import verify_email_html

    smtp_server = config["EMAIL_HOSTNAME"]
    port = 587
    username = config["SENDER_EMAIL"]
    password = config["EMAIL_PASSWORD"]
    from_addr = config["SENDER_EMAIL"]
    to_addr = receiver_email
    subject = (
        f"""Welcome to {organisation_details.get("org_name")} : verify your account"""
    )
    message = MIMEMultipart("alternative")
    message["From"] = from_addr
    message["To"] = to_addr
    message["Subject"] = subject
    html_content = MIMEText(
        verify_email_html(
            verification_url=verification_url,
            valid_till=valid_minute,
            organisation_details=organisation_details,
        ),
        "html",
        "utf-8",
    )
    message.attach(html_content)
    await aiosmtplib.send(
        message, hostname=smtp_server, port=port, password=password, username=username
    )
    return
