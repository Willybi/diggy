FROM python:3.13-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.13-slim
RUN useradd -m -u 1000 diggy
COPY --from=builder /root/.local /home/diggy/.local
ENV PATH=/home/diggy/.local/bin:$PATH
WORKDIR /app
COPY . .
RUN chown -R diggy:diggy /app
USER diggy
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
