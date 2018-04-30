drop table if exists user;
create table user (
  user_id blob primary key,
  username text not null,
  email text not null,
  pw_hash text not null
);

drop table if exists follower;
create table follower (
  who_id blob primary key,
  whom_id blob
);

drop table if exists message;
create table message (
  author_id blob,
  message_id text Primary key,
  text text not null,
  pub_date integer
);
