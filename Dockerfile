ARG PYTHON_VERSION=3.14-slim

FROM python:${PYTHON_VERSION}
# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /code

WORKDIR /code

# RUN pip install uv
COPY . /code
RUN uv sync --locked

EXPOSE 8000

CMD ["uv","run","gunicorn","fivehundredmagic.wsgi"]
