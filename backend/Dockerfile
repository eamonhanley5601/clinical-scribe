FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install the CPU-only PyTorch build first: this app never touches a GPU, but plain
# `pip install torch` (pulled in transitively by sentence-transformers) defaults to the
# CUDA build, dragging in ~6GB of nvidia-* runtime packages that are dead weight here --
# and were the actual cause of an EC2 build running out of memory/disk on a small instance.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so first request isn't slowed by it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
