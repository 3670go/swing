package com.swinganalyzer.shared.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "media")
public class MediaProperties {

	private long maxVideoBytes;
	private int signedReadTtlSeconds = 900;

	public long getMaxVideoBytes() {
		return maxVideoBytes;
	}

	public void setMaxVideoBytes(long maxVideoBytes) {
		this.maxVideoBytes = maxVideoBytes;
	}

	public int getSignedReadTtlSeconds() {
		return signedReadTtlSeconds;
	}

	public void setSignedReadTtlSeconds(int signedReadTtlSeconds) {
		this.signedReadTtlSeconds = signedReadTtlSeconds;
	}
}
