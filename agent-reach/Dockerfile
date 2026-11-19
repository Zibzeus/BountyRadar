FROM python:3.12-slim
ARG AGENT_REACH_REV=c70ae6da5d39bc90e09ad2ae0575ccc89f31e284
RUN pip install --no-cache-dir "https://codeload.github.com/Panniantong/Agent-Reach/zip/${AGENT_REACH_REV}" && useradd -r -u 11001 reader
WORKDIR /app
COPY server.py .
ENV PYTHONDONTWRITEBYTECODE=1
USER reader
EXPOSE 8787
CMD ["python", "server.py"]
