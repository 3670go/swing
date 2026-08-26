package com.swinganalyzer.media.infrastructure.persistence;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface MediaAssetJpaRepository extends JpaRepository<MediaAssetEntity, UUID> {

	List<MediaAssetEntity> findAllBySessionId(UUID sessionId);

	List<MediaAssetEntity> findAllByStoragePathIn(List<String> storagePaths);
}
