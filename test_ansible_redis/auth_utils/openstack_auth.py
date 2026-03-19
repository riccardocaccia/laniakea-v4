from keystoneauth1 import loading
from keystoneauth1 import session
import logging

logger = logging.getLogger(__name__)

def get_openstack_admin_creds():
    ''' 
    Application credentials retrieving.
    '''
    return get_secrets("SECRET/infrastructure/openstack/admin")

def get_keystone_token(aai_token, auth_url, project_id):
    """
    Exchange the AAI token with the OpenStack token for the deployment.
    """
    try:
        loader = loading.get_plugin_loader('v3oidcaccesstoken')
        
        auth = loader.load_from_options(
            auth_url=auth_url,
            # FIXME: insert a variables or make a new function for garr
            # now fixed recas
            identity_provider='recas-bari', 
            protocol='openid',
            access_token=aai_token,
            project_id=project_id
        )
        
        sess = session.Session(auth=auth, verify=True) 
        
        token_os = sess.get_token()
        logger.info("EXCHANGE: token AAI -> OpenStack completed!")
        return token_os

    except Exception as e:
        logger.error(f"ERROR [OpenStack Auth]: {e}")
        return None
