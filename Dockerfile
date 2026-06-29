# Streamlit app container for Hugging Face Spaces (Docker SDK).
# HF Spaces routes traffic to port 7860 and runs the container as a non-root
# user (UID 1000), so we listen on 7860 and keep writable state in /tmp.
FROM python:3.12-slim

# Streamlit runtime config: headless, correct port, no usage stats.
ENV HOME=/tmp \
    STREAMLIT_SERVER_PORT=7860 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

# --server.* flags are belt-and-suspenders alongside the env vars above.
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true"]
