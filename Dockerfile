# Render Cron Job image for the weekly Dad Mag edition. Runs scripts/run_cloud.sh.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    anthropic==0.77.0 \
    feedparser==6.0.12 \
    requests==2.32.5 \
    resend==2.21.0 \
    tzdata==2025.3

WORKDIR /app
COPY . .
RUN mkdir -p editions distro logs

CMD ["bash", "scripts/run_cloud.sh"]
