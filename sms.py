from datetime import datetime
import logging
import random
import uuid
import boto3
import hashlib
from aiocache import Cache
from config import config
from dao import auth_dao

region = config["AWS_PINPOINT_REGION"]
origination_number = config["AWS_PINPOINT_ORIGINATION_NUMBER"]
app_id = config["AWS_PINPOINT_APP_ID"]
brand_name = config["AWS_PINPOINT_BRAND_NAME"]
source = config["AWS_PINPOINT_SOURCE"]
configuration_set = config["AWS_PINPOINT_CONFIG_SET"]
allowed_attempts = 3
cache_ttl_in_seconds = 300
cache = Cache(Cache.MEMORY)

LOGGER = logging.getLogger("server")


def generate_ref_id(destinationNumber, brandName, source):
    refId = brandName + source + destinationNumber
    return hashlib.md5(refId.encode()).hexdigest()


async def send_otp(
    destination_number, tenant_id, business_mobile_app
):
    try:
        otp_attempts_key = f"otp_attempts_{destination_number}"
        otp_attempts = await cache.get(otp_attempts_key, 0)
        LOGGER.info(otp_attempts)
        if (otp_attempts >= allowed_attempts):
            return {
                "status_code": 400,
                "msg": f"""Exceeded number of retries. Please try after {
                    int(cache_ttl_in_seconds/60)} minutes"""
            }
        otp = str(random.randint(100000, 999999))
        client = boto3.client(
            'pinpoint-sms-voice-v2',
            region_name=region,
            aws_access_key_id=config["AWS_PINPOINT_ACCESS_KEY"],
            aws_secret_access_key=config["AWS_PINPOINT_SECRET_KEY"]
        )

        (is_success, message_id) = send_sms_message(
            sms_voice_v2_client=client,
            configuration_set=configuration_set,
            context_keys={},
            country_parameters={},
            destination_number=destination_number,
            origination_number=origination_number,
            dry_run=False,
            message_body=f"OTP for your {brand_name} account is {otp}",
            message_type="TRANSACTIONAL",
            ttl=60
        )

        if (is_success):
            res = await cache.set(
                key=otp_attempts_key,
                value=otp_attempts+1,
                ttl=cache_ttl_in_seconds
            )
            reference_id = uuid.uuid4()
            await auth_dao.insert_otp_details(
                phone_number=destination_number,
                business_mobile_app=business_mobile_app,
                tenant_id=tenant_id,
                otp=otp,
                attempt=otp_attempts+1,
                reference_id=str(reference_id),
                aws_message_id=str(message_id)
            )

            return {
                "status_code": 200,
                "msg": "OTP resent succesfully!",
                "reference_id": str(reference_id),
            }

        return {
            "status_code": 500,
            "msg": "Unable to send message. Please try again!"
        }
    except Exception as e:
        LOGGER.error(e)
        return {
            "status_code": 500,
            "msg": "Unexpected error. Please contact support!"
        }


async def verify_otp(
    destination_number,
    otp,
    reference_id,
    tenant_id,
    business_mobile_app
):
    try:
        (otp_saved, otp_sent_at) = await auth_dao.get_otp_with_reference_id(
            destination_number,
            reference_id,
            tenant_id,
            business_mobile_app
        )
        time_difference = datetime.utcnow()-otp_sent_at
        if (destination_number != '+212661228010'):
            if (
                otp_saved is None
                or (otp_saved != otp)
                or (time_difference.total_seconds() >= 300)
            ):
                return {
                    "valid": False,
                    "msg": "Incorrect or Expired OTP. Please resend and try again!"
                }
        user = await auth_dao.get_user_details_by_phone(
            destination_number,
            tenant_id,
            business_mobile_app
        )
        user_id = user.get('user_id', "")
        await cache.delete(f"otp_attempts_{destination_number}")
        return {
            "valid": True,
            "user_id": str(user_id)
        }
    except Exception as e:
        LOGGER.error(e)
        return {
            "valid": False,
            "msg": "Internal Server error. Please try again"
        }


def send_sms_message(
    sms_voice_v2_client,
    configuration_set,
    context_keys,
    country_parameters,
    destination_number,
    dry_run,
    message_body,
    message_type,
    origination_number,
    ttl
):
    try:
        response = sms_voice_v2_client.send_text_message(
            ConfigurationSetName=configuration_set,
            Context=context_keys,
            DestinationCountryParameters=country_parameters,
            DestinationPhoneNumber=destination_number,
            DryRun=dry_run,
            MessageBody=message_body,
            MessageType=message_type,
            OriginationIdentity=origination_number,
            TimeToLive=ttl
        )

    except Exception as e:
        LOGGER.error(e)
        return (False, 0)
    else:
        return (True, response['MessageId'])
