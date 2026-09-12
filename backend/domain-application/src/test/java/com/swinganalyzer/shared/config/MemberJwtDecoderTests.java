package com.swinganalyzer.shared.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.gen.ECKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;

class MemberJwtDecoderTests {

	@Test
	void decodesSupabaseEs256Token() throws Exception {
		ECKey signingKey = new ECKeyGenerator(Curve.P_256)
				.keyID("supabase-test-key")
				.generate();
		HttpServer jwkServer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
		byte[] jwkSet = new JWKSet(signingKey.toPublicJWK())
				.toString()
				.getBytes(StandardCharsets.UTF_8);
		jwkServer.createContext("/jwks", exchange -> {
			exchange.getResponseHeaders().set("Content-Type", "application/json");
			exchange.sendResponseHeaders(200, jwkSet.length);
			try (var body = exchange.getResponseBody()) {
				body.write(jwkSet);
			}
		});
		jwkServer.start();

		try {
			String issuer = "https://example.supabase.co/auth/v1";
			MemberAuthProperties properties = new MemberAuthProperties();
			properties.setJwkSetUri("http://127.0.0.1:" + jwkServer.getAddress().getPort() + "/jwks");
			properties.setIssuer(issuer);
			properties.setAudience("authenticated");
			JwtDecoder decoder = new MemberSecurityConfiguration().memberJwtDecoder(properties);

			Instant now = Instant.now();
			SignedJWT token = new SignedJWT(
					new JWSHeader.Builder(JWSAlgorithm.ES256)
							.type(JOSEObjectType.JWT)
							.keyID(signingKey.getKeyID())
							.build(),
					new JWTClaimsSet.Builder()
							.subject("member-subject")
							.issuer(issuer)
							.audience("authenticated")
							.issueTime(Date.from(now.minusSeconds(5)))
							.expirationTime(Date.from(now.plusSeconds(300)))
							.claim("role", "authenticated")
							.build());
			token.sign(new ECDSASigner(signingKey));

			Jwt decoded = decoder.decode(token.serialize());

			assertThat(decoded.getSubject()).isEqualTo("member-subject");
			assertThat(decoded.getAudience()).containsExactly("authenticated");
			assertThat(decoded.getClaimAsString("role")).isEqualTo("authenticated");
		} finally {
			jwkServer.stop(0);
		}
	}
}
