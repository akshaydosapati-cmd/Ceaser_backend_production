import logging

from app.services.cloud_runtime.worker import CloudWorker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    CloudWorker().serve_forever()
