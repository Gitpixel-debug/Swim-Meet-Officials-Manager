import logging
from threading import Thread
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings

logger = logging.getLogger(__name__)


def execute_in_background(function):
    def start_thread(*args, **kwargs):
        thread = Thread(target=function, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()

    return start_thread


@execute_in_background
def send_email(html_template, context):
    from_email = context.get('from_email') or settings.DEFAULT_FROM_EMAIL
    subject = context.get('subject') or ''
    to_email = context.get('to_email')
    cc = context.get('cc')
    bcc = context.get('bcc')
    attachments = context.get('attachments')

    if not to_email:
        raise ValueError("The 'to_email' address must be provided and cannot be empty.")
    if not isinstance(to_email, list):
        to_email = [to_email]

    try:
        html_message = render_to_string(html_template, context)
        message = EmailMessage(subject=subject, body=html_message, from_email=from_email, to=to_email, cc=cc, bcc=bcc,
                               attachments=attachments)
        message.content_subtype = 'html'
        result = message.send()
        logger.info(f"Sending email to {', '.join(to_email)} with subject: {subject} - Status {result}")
    except Exception as e:
        logger.info(f"Sending email to {', '.join(to_email)} with subject: {subject} - Status 0")
        logger.exception(e)
