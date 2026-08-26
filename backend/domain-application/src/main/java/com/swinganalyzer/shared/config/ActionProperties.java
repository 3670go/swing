package com.swinganalyzer.shared.config;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "action")
public class ActionProperties {

	private String apiKey = "";
	private List<String> fileHosts = new ArrayList<>();

	public String getApiKey() {
		return apiKey;
	}

	public void setApiKey(String apiKey) {
		this.apiKey = apiKey;
	}

	public List<String> getFileHosts() {
		return fileHosts;
	}

	public void setFileHosts(List<String> fileHosts) {
		this.fileHosts = fileHosts;
	}
}
