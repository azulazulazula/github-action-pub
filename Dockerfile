FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/hello-world.jar /app/hello-world.jar
EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "-jar", "/app/hello-world.jar"]
