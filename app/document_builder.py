"""Build in-memory DOCX files for forwarded Telegram posts."""

from collections.abc import Sequence
from io import BytesIO

from docx import Document

from app.telegram_media import DownloadedPhoto
from app.telegram_parser import ForwardedPost

MAX_TITLE_LENGTH = 150


def _post_content(post: ForwardedPost) -> str:
    return post.text or post.caption or ""


def build_document_title(post: ForwardedPost) -> str:
    """Build a compact, single-line title from available post metadata."""
    date_part = (
        post.source_date.strftime("%Y-%m-%d")
        if post.source_date
        else "Telegram post"
    )
    parts = [date_part]
    if post.source_chat_title:
        parts.append(" ".join(post.source_chat_title.split()))

    first_line = next(
        (
            " ".join(line.split())
            for line in _post_content(post).splitlines()
            if line.strip()
        ),
        "",
    )
    if first_line:
        parts.append(first_line)

    title = " — ".join(parts)
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    return title[: MAX_TITLE_LENGTH - 1].rstrip() + "…"


class DocumentImageError(RuntimeError):
    """A photo could not be embedded in the archive document."""


def build_post_docx(
    post: ForwardedPost,
    photos: Sequence[DownloadedPhoto] = (),
) -> BytesIO:
    """Return a seekable DOCX stream containing post text and photos."""
    title = build_document_title(post)
    document = Document()
    document.add_heading(title, level=1)

    source = post.source_chat_title or "недоступен"
    if post.source_chat_username:
        source = f"{source} (@{post.source_chat_username})"
    published = (
        post.source_date.strftime("%d.%m.%Y %H:%M")
        if post.source_date
        else "недоступно"
    )
    document.add_paragraph(f"Источник: {source}")
    document.add_paragraph(f"Опубликовано: {published}")
    document.add_paragraph(f"Оригинал: {post.source_url or 'недоступен'}")
    document.add_paragraph("—")

    content = _post_content(post)
    if content:
        for paragraph in content.split("\n"):
            document.add_paragraph(paragraph)

    if photos:
        document.add_paragraph()
        document.add_heading("Изображения", level=2)
        section = document.sections[0]
        available_width = (
            section.page_width
            - section.left_margin
            - section.right_margin
        )
        try:
            for photo in photos:
                document.add_picture(
                    BytesIO(photo.data),
                    width=available_width,
                )
        except Exception as error:
            raise DocumentImageError(
                "Could not embed a Telegram photo in DOCX"
            ) from error

    document.add_paragraph("Сохранено через Telegram Archive Bot")
    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream
