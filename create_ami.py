import boto3
import os
import argparse
import time
import random

# Welcome

def get_latest_ecs_optimized_ami(region):
    ssm_client = boto3.client('ssm', region_name=region)
    response = ssm_client.get_parameter(
        Name='/aws/service/ecs/optimized-ami/amazon-linux/recommended/image_id',
        WithDecryption=False
    )
    return response['Parameter']['Value']


def save_image(instance_id, options):
    print("Saving {0} as image {1}".format(instance_id, options.image_name))
    time.sleep(15)  # sleep another 15 seconds to give time to run user_data script.
    ec2_client = boto3.client('ec2', region_name=options.region)
    response = ec2_client.create_image(
        Description=options.image_description,
        InstanceId=instance_id,
        Name=options.image_name,
        NoReboot=False)
    print("Saved image {0}".format(response["ImageId"]))
    return response["ImageId"]


def check_instance(instance_id, options):
    ec2_client = boto3.client('ec2', region_name=options.region)
    response = ec2_client.describe_instance_status(InstanceIds=[instance_id])
    try:
        status = response['InstanceStatuses'][0]['InstanceState']['Name']
    except IndexError:
        status = "NA"
    return status


def check_image(image_id, options):
    ec2_client = boto3.client('ec2', region_name=options.region)
    response = ec2_client.describe_images(ImageIds=[image_id])
    status = response["Images"][0]["State"]
    return status


def terminate_instance(instance_id, options):
    ec2_client = boto3.client('ec2', region_name=options.region)
    response = ec2_client.terminate_instances(InstanceIds=[instance_id])
    print("Killed instance {0}".format(instance_id))


def create_instance(options):
    print("Creating instance")
    ec2_client = boto3.client('ec2', region_name=options.region)

    user_data = "#!/bin/bash\n"
    user_data += "yum install -y aws-cli\n"
    user_data += "aws s3 cp {0} /etc/ecs/ecs.config\n".format(options.ecs_config_file)
    user_data += """echo 'OPTIONS="${OPTIONS} --storage-opt dm.basesize=%dG"' >> /etc/sysconfig/docker\n""" % (int(options.docker_dm_basesize))
    user_data += "sudo mkdir /mnt"
    user_data += "sudo service docker stop\n"
    user_data += "sudo service docker start\n"
    response = ec2_client.run_instances(
        ImageId=get_latest_ecs_optimized_ami(options.region),
        InstanceType=options.instance_type,
        KeyName=options.key_name,
        ClientToken=str(random.randint(0, 1000)),
        MaxCount=1,
        MinCount=1,
        UserData=user_data,
        SecurityGroupIds=options.security_group_ids,
        DisableApiTermination=False,
        EbsOptimized=options.ebs_optimized,
        IamInstanceProfile={
            'Name': options.iam_instance_profile
        },
        # InstanceInitiatedShutdownBehavior=options.instance_shutdown_behavior,
        # InstanceMarketOptions=InstanceMarketOptions,
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/xvda',
                'Ebs': {
                    'VolumeSize': int(options.root_volume_size),
                    'VolumeType': 'gp2'
                },
            },
            {
                'DeviceName': '/dev/xvdcz',
                'Ebs': {
                    'Encrypted': options.encrypt_docker_volume,
                    'VolumeSize': int(options.docker_volume_size),
                    'VolumeType': 'gp2'
                },
            },
        ],
    )
    # print(response)
    instance_id = response["Instances"][0]["InstanceId"]
    print("Instance {0} created.".format(instance_id))
    return instance_id

if __name__ == "__main__":
    # Note to user. Basically really only need to provide --image_name , --docker_dm_basesize, --ebs_optimized, --encrypt_docker_volume. Everything else is
    # redefined at time of AWS Batch job creation
    print("Entering create AMI script. This process can take up to 10 min.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--region", action="store", required=True, choices=["us-west-1", "us-east-1", "us-west-2", "us-east-2"], help="aws region")
    parser.add_argument("--instance_type", action="store", default="t2.micro", help="ec2 instance type")
    parser.add_argument("--key_name", action="store", required=True, help="aws key_pair name for creating an instance")
    parser.add_argument("--image_name", action="store", required=True, help="A name for the new image.")
    parser.add_argument("--image_description", action="store", default="automated_ecs_image", help="A description for the new image")
    parser.add_argument("--ecs_config_file", action="store", required=True, help="full bucket and path of your ecs.config file located on amazon s3 (ie s3://bucket/path/to/ecs.config)")
    parser.add_argument("--docker_dm_basesize", action="store", default=10, help="in GB how much space is allocated to each running container")
    parser.add_argument("--docker_volume_size", action="store", default=22, help="in GB")
    parser.add_argument("--root_volume_size", action="store", default=8, help="in GB")
    parser.add_argument("--encrypt_docker_volume", action="store_true", help="Indicates whether the EBS volume is encrypted")
    parser.add_argument("--ebs_optimized", action="store_true", help="Indicates whether the instance is optimized for Amazon EBS I/O")
    parser.add_argument("--iam_instance_profile", action="store", default="ecsInstanceRole", help="The name of the IAM instance profile.")
    parser.add_argument("--security_group_ids", action="store", nargs="*", help="One or more security group IDs.")
    options = parser.parse_args()

    instance_id = create_instance(options)

    isRunning = False
    checks = 0
    while (not isRunning and checks < 5):
        health = check_instance(instance_id, options)
        if health == "NA":
            checks += 1
        print("Instance status is: {0}".format(health))
        if health.lower() == "running":
            isRunning = True
        print("Sleeping for 15 seconds")
        time.sleep(15)

    image_id = save_image(instance_id, options)

    isAvailable = False
    checks = 0
    while (not isAvailable and checks < 5):
        health = check_image(image_id, options)
        if health == "NA":
            checks += 1
        print("Image status is: {0}".format(health))
        if health.lower() == "available":
            isAvailable = True
        print("Sleeping for 15 seconds")
        time.sleep(15)

    terminate_instance(instance_id, options)
    print("DONE!")
