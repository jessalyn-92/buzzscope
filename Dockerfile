FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY .streamlit ./.streamlit
# Bake the synthetic datasets in so the offline demo works with no network at all.
RUN buzzscope gen-data

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "src/buzzscope/app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
