import datetime
import json
from pprint import pprint

import argparse
import logging
import sys
import yaml

from wekapyutils.wekalogging import configure_logging, register_module
from wekapyutils.wekatime import datetime_to_wekatime, wekatime_to_datetime
#from wekapyutils.wekassh import RemoteServer, parallel

import wekarestapi
from wekarestapi import LoginRefreshBody
from wekarestapi.rest import ApiException

# get root logger
import auth_token

log = logging.getLogger()


def setup_log_file(events_log_file, log_file_size_mb, num_log_files):

    events_log = logging.getLogger("events_log")
    log.info(f"Setting up event log {events_log_file}")

    snaptool_f_handler = logging.handlers.RotatingFileHandler(events_log_file,
                                                              maxBytes=log_file_size_mb * 1024 * 1024,
                                                              backupCount=num_log_files)
    snaptool_f_handler.setFormatter(logging.Formatter('%(message)s'))
    events_log.addHandler(snaptool_f_handler)
    events_log.setLevel(logging.INFO)
    # events_log file is intended for high level action logging (create/delete snapshots, etc, distinct
    # from other logging), so don't propagate to root logger
    events_log.propagate = False

def main():
    # parse arguments
    progname = sys.argv[0]
    parser = argparse.ArgumentParser(description='This is a stub for programs that would use the Weka REST api')

    # example of how to to add a list-type command line argument
    #parser.add_argument('server_ips', metavar='serverips', type=str, nargs='+',
    #                    help='Server DATAPLANE IPs to test')

    # example of how to add a switch-line argument
    #parser.add_argument("-j", "--json", dest='json_flag', action='store_true', help="enable json output mode")


    # these next args are passed to the script and parsed in etc/preamble - this is more for syntax checking
    parser.add_argument("-v", "--verbose", dest='verbosity', action='store_true', help="enable verbose mode")

    args = parser.parse_args()

    # set up logging in a standard way...
    configure_logging(log, args.verbosity)

    # local modules - override a module's logging level
    register_module("my_module", logging.ERROR)

    with open("weka_event_logger.yml", 'r') as f:
        config = yaml.load(stream=f, Loader=yaml.BaseLoader)

    # need to do this a better way...
    try:
        loginfo = config['events_log']
        clusterinfo = config['cluster']
    except KeyError:
        print(f"malformed configuration file, exiting")
        sys.exit(1)

    try:
        logfile_name = loginfo['filename']
    except KeyError:
        logfile_name = "weka_events.log"

    try:
        logsize = int(loginfo['size_mb'])
    except KeyError:
        logsize = 10

    try:
        num_logs = int(loginfo['num_files'])
    except KeyError:
        num_logs = 6

    try:
        cluster_hosts = clusterinfo['hosts']
    except KeyError:
        log.critical("No hosts defined in config file, exiting")
        sys.exit(1)

    try:
        username = clusterinfo['username'] if len(clusterinfo['username']) > 0 else None
    except KeyError:
        log.info("No username defined in config file")
        username = None

    try:
        password = clusterinfo['password'] if len(clusterinfo['password']) > 0 else None
    except KeyError:
        log.info("No password defined in config file")
        password = None

    try:
        org = clusterinfo['organization'] if len(clusterinfo['organization']) > 0 else "root"
    except KeyError:
        log.info("No organization defined in config file")
        org = "root"   # provide default

    try:
        auth_token_file = clusterinfo['auth_token_file']
        auth_tokens = auth_token.get_tokens(auth_token_file)
    except KeyError:
        log.info("No auth_token_file defined in config file")
        auth_tokens = None

    if username is None and password is None and auth_tokens is None:
        log.critical("No cluster credentials provided in config file, exiting")
        sys.exit(1)


    setup_log_file(logfile_name, logsize, num_logs)
    events_log = logging.getLogger("events_log")

    try:
        sleep_interval = int(loginfo['fetch_every_secs'])
    except KeyError:
        sleep_interval = 60

    # try the hosts to see which is up and we can log in there...
    for host in cluster_hosts.split(','):
        weka_config = wekarestapi.Configuration(hostname=host)

        # create an instance of the API class
        api_client = wekarestapi.ApiClient(weka_config)

        if auth_tokens is not None:
            try:
                api_response = wekarestapi.LoginApi(api_client).refresh_token(
                        LoginRefreshBody(refresh_token=auth_tokens['refresh_token']))
            except ApiException as e:
                log.info("Exception when calling LoginApi->login: %s\n" % e)






        try:
            # login to weka system
            api_response = wekarestapi.LoginApi(api_client).login(
                wekarestapi.LoginBody(username=username,
                                      password=password,
                                      org=org))
            #    pprint(api_response)
            weka_config.auth_tokens = api_response.data
        except ApiException as e:
            print("Exception when calling LoginApi->login: %s\n" % e)

    # initial start and end times - the last minute's events by default
    end_time = datetime_to_wekatime(datetime.datetime.utcnow())
    start_time = datetime_to_wekatime(datetime.datetime.utcnow() - datetime.timedelta(seconds=(0-sleep_interval)))

    try:
        # get alerts
        api_response = wekarestapi.EventsApi(api_client).get_events(start_time=start_time, end_time=end_time)
        for entry in api_response.data:
            events_log.critical(json.dumps(entry.to_dict()))
    except ApiException as e:
        print("Exception when calling AlertsApi->get_alerts: %s\n" % e)

    print()

if __name__ == '__main__':
    main()
