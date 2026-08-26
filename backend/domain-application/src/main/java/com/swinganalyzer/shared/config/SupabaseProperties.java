package com.swinganalyzer.shared.config;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "supabase")
public class SupabaseProperties {

	private URI url;
	private String secretKey = "";
	private String storageBucket = "swing-media";

	public URI getUrl() {
		return url;
	}

	public void setUrl(URI url) {
		this.url = url;
	}

	public String getSecretKey() {
		return secretKey;
	}

	public void setSecretKey(String secretKey) {
		this.secretKey = secretKey;
	}

	public String getStorageBucket() {
		return storageBucket;
	}

	public void setStorageBucket(String storageBucket) {
		this.storageBucket = storageBucket;
	}
}
