# Rebuild trigger


FROM python:3.10-slim

# Install dependensi dasar
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Buat virtualenv
WORKDIR /app
COPY . /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install pip dan package
# Install pip dan package dalam virtualenv
RUN /opt/venv/bin/pip install --upgrade pip
RUN /opt/venv/bin/pip install -r requirements.txt
RUN /opt/venv/bin/pip install aiogram==2.25.2

RUN /opt/venv/bin/pip freeze

CMD ["/opt/venv/bin/python3", "bot.py"]