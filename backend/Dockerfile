# Two stages, because the compiler that builds a wheel has no business being in the image
# that serves traffic. The builder produces wheels; the runtime installs them and carries
# nothing but curl (the healthcheck) and the application.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl only: it is what the compose healthcheck runs.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 befos \
    && useradd --system --uid 10001 --gid befos --home-dir /app --shell /usr/sbin/nologin befos

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

# The named volume is mounted over this path, so its ownership comes from the directory as
# it stands in the image — which is why the chown happens before the user switch.
RUN mkdir -p /app/uploads && chown -R 10001:10001 /app

USER befos

EXPOSE 8000

# The same trust boundary the compose command states, stated here too: anyone running this
# image directly (`docker run`) gets the limiter's rule as `app/core/rate_limit.py` writes it,
# not uvicorn's default of replacing the peer address with X-Forwarded-For for loopback peers.
# Measured on the stand: 300 requests rotating 30 header identities from the container's own
# loopback answered all 300 against a 120/minute ceiling.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
