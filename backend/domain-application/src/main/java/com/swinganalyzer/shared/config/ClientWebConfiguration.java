package com.swinganalyzer.shared.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientWebProperties.class)
public class ClientWebConfiguration implements WebMvcConfigurer {

	private final ClientWebProperties properties;

	public ClientWebConfiguration(ClientWebProperties properties) {
		this.properties = properties;
	}

	@Override
	public void addCorsMappings(CorsRegistry registry) {
		registry.addMapping("/**")
				.allowedOrigins(properties.getCorsOrigins().toArray(String[]::new))
				.allowedMethods("GET", "POST", "DELETE", "OPTIONS")
				.allowedHeaders("Content-Type");
	}
}
