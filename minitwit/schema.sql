drop table if exists user;
create table user (
  user_id GUID primary key,
  username text not null,
  email text not null,
  pw_hash text not null
);

drop table if exists follower;
create table follower (
  who_id GUID NOT NULL,
  whom_id GUID primary key
);

drop table if exists message;
create table message (
  author_id GUID,
  message_id GUID Primary key,
  text text not null,
  pub_date integer
);
