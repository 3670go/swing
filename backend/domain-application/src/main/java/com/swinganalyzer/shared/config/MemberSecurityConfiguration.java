package com.swinganalyzer.shared.config;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableConfigurationProperties(MemberAuthProperties.class)
public class MemberSecurityConfiguration {

	@Bean
	@Order(1)
	SecurityFilterChain actionSecurity(HttpSecurity http) throws Exception {
		http.securityMatcher("/v1/actions/**")
				.csrf(csrf -> csrf.disable())
				.authorizeHttpRequests(requests -> requests.anyRequest().permitAll());
		return http.build();
	}

	@Bean
	@Order(2)
	SecurityFilterChain applicationSecurity(
			HttpSecurity http,
			MemberAuthenticationEntryPoint authenticationEntryPoint) throws Exception {
		http.csrf(csrf -> csrf.disable())
				.cors(Customizer.withDefaults())
				.sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
				.authorizeHttpRequests(requests -> requests
						.requestMatchers("/v1/me/**").authenticated()
						.anyRequest().permitAll())
				.oauth2ResourceServer(oauth -> oauth
						.jwt(Customizer.withDefaults())
						.authenticationEntryPoint(authenticationEntryPoint));
		return http.build();
	}

	@Bean
	JwtDecoder memberJwtDecoder(MemberAuthProperties properties) {
		if (properties.getJwkSetUri().isBlank() || properties.getIssuer().isBlank()) {
			return token -> {
				throw new BadJwtException("Member authentication is not configured");
			};
		}

		NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(properties.getJwkSetUri())
				.jwsAlgorithm(SignatureAlgorithm.ES256)
				.build();
		List<OAuth2TokenValidator<Jwt>> validators = new ArrayList<>();
		validators.add(JwtValidators.createDefaultWithIssuer(properties.getIssuer()));
		validators.add(requiredSubject());
		if (!properties.getAudience().isBlank()) {
			validators.add(requiredAudience(properties.getAudience()));
		}
		decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(validators));
		return decoder;
	}

	private static OAuth2TokenValidator<Jwt> requiredAudience(String audience) {
		return jwt -> jwt.getAudience().contains(audience)
				? OAuth2TokenValidatorResult.success()
				: OAuth2TokenValidatorResult.failure(new OAuth2Error(
						"invalid_token", "Required audience is missing", null));
	}

	private static OAuth2TokenValidator<Jwt> requiredSubject() {
		return jwt -> jwt.getSubject() != null && !jwt.getSubject().isBlank()
				? OAuth2TokenValidatorResult.success()
				: OAuth2TokenValidatorResult.failure(new OAuth2Error(
						"invalid_token", "Subject is missing", null));
	}
}
