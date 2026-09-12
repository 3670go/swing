package com.swinganalyzer.shared.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
		"spring.datasource.url=jdbc:h2:mem:member-security;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
		"spring.datasource.username=sa",
		"spring.datasource.password=",
		"spring.jpa.hibernate.ddl-auto=create-drop",
		"spring.flyway.enabled=false"
})
@AutoConfigureMockMvc
class MemberSecurityIntegrationTests {

	@Autowired
	private MockMvc mvc;

	@Test
	void memberApiRequiresAuthenticationWithStableErrorBody() throws Exception {
		mvc.perform(get("/v1/me/profile"))
				.andExpect(status().isUnauthorized())
				.andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
				.andExpect(content().json("{\"detail\":\"AUTHENTICATION_REQUIRED\"}"));
	}

	@Test
	void publicChatIsNotBlockedByMemberAuthentication() throws Exception {
		int responseStatus = mvc.perform(post("/v1/chat")
				.contentType(MediaType.APPLICATION_JSON)
				.content("{}"))
				.andReturn()
				.getResponse()
				.getStatus();

		assertThat(responseStatus).isNotEqualTo(401);
	}

	@Test
	void memberProfilePreflightAllowsPutAndAuthorizationHeader() throws Exception {
		mvc.perform(options("/v1/me/profile")
				.header("Origin", "http://127.0.0.1:4173")
				.header("Access-Control-Request-Method", "PUT")
				.header("Access-Control-Request-Headers", "authorization,content-type"))
				.andExpect(status().isOk())
				.andExpect(header().string("Access-Control-Allow-Origin", "http://127.0.0.1:4173"))
				.andExpect(header().string("Access-Control-Allow-Methods", org.hamcrest.Matchers.containsString("PUT")))
				.andExpect(header().string("Access-Control-Allow-Headers", org.hamcrest.Matchers.containsStringIgnoringCase("authorization")));
	}
}
