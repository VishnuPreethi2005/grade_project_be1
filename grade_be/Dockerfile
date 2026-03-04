FROM smarteduagent.azurecr.io/base:prod-v1

ENV DJANGO_SETTINGS_MODULE=promptRightProd.deployment_settings \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

RUN groupadd -r django && useradd -r -g django django && \
    mkdir -p /app/media /app/staticfiles && \
    chown -R django:django /app

USER django

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "promptRightProd.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120"]
