package com.swinganalyzer.media.application;

import java.net.URI;
import java.util.List;

public interface MediaStorage {

	void upload(String objectPath, PreparedMedia media);

	URI createSignedReadUrl(String objectPath);

	void deleteMany(List<String> objectPaths);
}
