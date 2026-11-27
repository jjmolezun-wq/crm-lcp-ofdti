FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8000 HOST=0.0.0.0 CRM_LCP_PROD=1
EXPOSE 8000
CMD ["python3", "app.py"]
