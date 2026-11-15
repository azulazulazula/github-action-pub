package hello;

import java.net.HttpURLConnection;
import java.net.URI;

public final class HealthCheck {
    private HealthCheck() {
    }

    public static void main(String[] args) {
        try {
            HttpURLConnection connection = (HttpURLConnection) URI
                    .create("http://127.0.0.1:8080/")
                    .toURL()
                    .openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(2000);
            connection.setReadTimeout(2000);
            int status = connection.getResponseCode();
            connection.disconnect();
            if (status != 200) {
                System.exit(1);
            }
        } catch (Exception e) {
            System.exit(1);
        }
    }
}
