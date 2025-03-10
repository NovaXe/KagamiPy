FROM python:3.13.2-slim

WORKDIR /kagami

COPY . .
#COPY requirements.txt .
# RUN pip install --upgrade pip
RUN pip install -r requirements.txt
#  --force-reinstall

# COPY requirements.txt requirements.txt
# pip install --update pip; \

#RUN --mount=type=cache,target=/root/.cache/pip \
#    --mount=type=bind,source=requirements.txt,target=requirements.txt \
#    python -m pip install -r requirements.txt


# Switch to the non-privileged user to run the application.
#USER appuser

#RUN chmod 777

# Copy the source code into the container.


# Run the application.
#CMD python3 -m main
CMD ["python", "-u","main.py"]
