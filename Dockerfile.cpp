FROM gcc:latest
RUN apt update && apt install -y time
WORKDIR /app
CMD ["bash"]