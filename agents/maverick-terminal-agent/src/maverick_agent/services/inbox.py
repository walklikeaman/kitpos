from __future__ import annotations

from dataclasses import dataclass
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.message import EmailMessage
import imaplib
from pathlib import Path
import tempfile

from maverick_agent.models import AttachmentCandidate


@dataclass(slots=True)
class ImapInboxClient:
    host: str
    port: int
    username: str
    password: str
    mailbox: str = "INBOX"
    scan_limit: int = 50

    def find_latest_var_pdf(self, merchant_id: str) -> AttachmentCandidate | None:
        with imaplib.IMAP4_SSL(self.host, self.port) as client:
            client.login(self.username, self.password)
            client.select(self.mailbox)
            status, data = client.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                return None

            ids = data[0].split()
            for msg_id in reversed(ids[-self.scan_limit:]):
                status, msg_data = client.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                message = message_from_bytes(msg_data[0][1], policy=policy.default)
                haystack = self._message_haystack(message)
                if merchant_id.casefold() not in haystack.casefold():
                    continue

                attachment = self._download_first_pdf(message)
                if attachment:
                    return attachment
        return None

    @staticmethod
    def _message_haystack(message: EmailMessage) -> str:
        subject = str(make_header(decode_header(message.get("subject", ""))))
        sender = message.get("from", "")
        parts = [subject, sender]
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="ignore"))
        else:
            payload = message.get_payload(decode=True) or b""
            charset = message.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="ignore"))
        return "\n".join(parts)

    @staticmethod
    def _download_first_pdf(message: EmailMessage) -> AttachmentCandidate | None:
        for part in message.iter_attachments():
            filename = part.get_filename() or "attachment.pdf"
            if not filename.lower().endswith(".pdf"):
                continue
            payload = part.get_payload(decode=True) or b""
            target_dir = Path(tempfile.mkdtemp(prefix="maverick-agent-"))
            target_path = target_dir / filename
            target_path.write_bytes(payload)
            subject = str(make_header(decode_header(message.get("subject", ""))))
            sender = message.get("from", "")
            return AttachmentCandidate(
                filename=filename,
                path=target_path,
                subject=subject,
                sender=sender,
            )
        return None

