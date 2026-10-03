FROM python:3.12-slim
WORKDIR /app
COPY main.py .
COPY dist ./dist
ENV HOST=0.0.0.0 PORT=3000 DATABASE_PATH=/app/data/game.sqlite3
RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 3000
CMD ["python", "main.py"]
