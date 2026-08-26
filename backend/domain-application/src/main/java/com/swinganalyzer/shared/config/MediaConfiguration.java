package com.swinganalyzer.shared.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({ SupabaseProperties.class, MediaProperties.class, ActionProperties.class })
public class MediaConfiguration {
}
