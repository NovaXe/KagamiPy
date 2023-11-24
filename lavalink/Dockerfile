FROM openjdk:17-alpine

WORKDIR /opt/Lavalink

COPY Lavalink.jar Lavalink.jar
COPY application.yml application.yml

EXPOSE 4762

CMD ["java", "-jar", "Lavalink.jar"]