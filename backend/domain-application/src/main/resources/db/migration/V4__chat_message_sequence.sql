ALTER TABLE chat_messages
    ADD COLUMN sequence_number bigint GENERATED ALWAYS AS IDENTITY;

CREATE UNIQUE INDEX ux_chat_messages_sequence_number
    ON chat_messages(sequence_number);
