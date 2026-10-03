FROM python:3.12-slim
WORKDIR /usr/src/otongifts
COPY main.py asset_store.py ./
COPY public/ ./public/
ENV HOST=0.0.0.0 PORT=3000 DATABASE_PATH=/app/data/game.sqlite3
RUN mkdir -p /app/data
EXPOSE 3000
CMD ["python", "main.py"]
