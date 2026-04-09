from flask_mail import Message
from app import mail

def send_email(subject, recipient, body):
    msg = Message(
        subject=subject,
        recipients=[recipient],
        body=body,
        sender="kandregulayajath.22.csm@anits.edu.in"
    )
    mail.send(msg)

# sgkm dmqk jewg wiyh