from jinja2 import Template


def render_html(template_str: str, context: dict) -> str:
    template = Template(template_str)
    return template.render(**context)
