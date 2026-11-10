FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY radar ./radar
COPY tests ./tests
# /site com um arquivo dentro: o Docker copia o conteúdo E o dono para o volume novo,
# então o site consegue gravar sem ajuste manual de permissão.
RUN useradd -r -u 10001 radar && mkdir /site && touch /site/.keep && chown -R radar /site
USER radar
CMD ["python", "-m", "radar.main"]
