# create_ami
Automated script to create amazon ami for ECS instances (works well with AWS BATCH and ECS)

create_ami.py is a script for the automated creation of custom ECS AMI's, which are suitable for AWS Batch jobs and AWS ECS services. 
It pulls the latest official ECS AMI image for the user from AWS, and allows the user to customize the image with arguments such as encryption, 
volume size for both root and docker, docker container size, etc. It allows the user also to provide a custom ecs config file, which can specifiy things such as 
ECS_IMAGE_PULL_BEHAVIOR, ECS_IMAGE_CLEANUP_INTERVAL, etc.
