package com.swinganalyzer.shared.config;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public class ClientWebProperties {

	private List<String> corsOrigins = new ArrayList<>();

	public List<String> getCorsOrigins() {
		return corsOrigins;
	}

	public void setCorsOrigins(List<String> corsOrigins) {
		this.corsOrigins = corsOrigins;
	}
}
