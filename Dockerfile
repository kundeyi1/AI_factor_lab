FROM python:3.11-slim

RUN useradd -m -u 1000 user

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    QUANT_DATA_ROOT=/home/user/data \
    AI_FACTOR_LAB_CACHE_DIR=/home/user/data/data_cache \
    AI_FACTOR_LAB_OFFLINE_DATA_ONLY=true \
    HF_HOME=/home/user/.cache/huggingface \
    PORT=7860

WORKDIR $HOME/app

COPY --chown=user requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN mkdir -p "$QUANT_DATA_ROOT" "$AI_FACTOR_LAB_CACHE_DIR" "$HF_HOME"

EXPOSE 7860

CMD ["python", "scripts/start_hf.py"]
