import logging

logger = logging.getLogger(__name__)


def render_pdf(html_content: str, output_path: str) -> str:
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return output_path
    except ImportError:
        logger.error("WeasyPrint not installed. Install with: pip install weasyprint")
        raise
