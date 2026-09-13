-- SQL Script to initialize required databases for Role-Sync microservices

CREATE DATABASE "rolesync-micro-authservice";
CREATE DATABASE "rolesync-micro-workspace";
CREATE DATABASE "rolesync-micro-catalog";
CREATE DATABASE "rolesync-micro-sales-agent";
-- RAG: pgvector-backed chunks, parents and lineage. data-pipeline enables the
-- `vector` extension inside this database on startup.
CREATE DATABASE "rolesync-micro-rag";
