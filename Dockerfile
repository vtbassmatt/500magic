ARG PYTHON_VERSION=3.14-slim

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /code

WORKDIR /code

RUN pip install uv
COPY pyproject.toml uv.lock /code/
RUN uv sync --system
COPY . /code

EXPOSE 8000

CMD ["uv","run","python","manage.py","runserver","0.0.0.0:8000"]
