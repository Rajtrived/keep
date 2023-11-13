"""
Datadog Provider is a class that allows to ingest/digest data from Datadog.
"""
import dataclasses
import datetime
import json
import os
import random
import re
import time

import pydantic
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.api_client import Endpoint
from datadog_api_client.exceptions import (
    ApiException,
    ForbiddenException,
    NotFoundException,
)
from datadog_api_client.v1.api.events_api import EventsApi
from datadog_api_client.v1.api.logs_api import LogsApi
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.api.monitors_api import MonitorsApi
from datadog_api_client.v1.api.webhooks_integration_api import WebhooksIntegrationApi
from datadog_api_client.v1.model.monitor import Monitor
from datadog_api_client.v1.model.monitor_options import MonitorOptions
from datadog_api_client.v1.model.monitor_thresholds import MonitorThresholds
from datadog_api_client.v1.model.monitor_type import MonitorType

from keep.api.models.alert import AlertDto
from keep.contextmanager.contextmanager import ContextManager
from keep.providers.base.base_provider import BaseProvider
from keep.providers.base.provider_exceptions import GetAlertException
from keep.providers.datadog_provider.datadog_alert_format_description import (
    DatadogAlertFormatDescription,
)
from keep.providers.models.provider_config import ProviderConfig, ProviderScope
from keep.providers.models.provider_method import ProviderMethod
from keep.providers.providers_factory import ProvidersFactory


@pydantic.dataclasses.dataclass
class DatadogProviderAuthConfig:
    """
    Datadog authentication configuration.
    """

    KEEP_DATADOG_WEBHOOK_INTEGRATION_NAME = "keep-datadog-webhook-integration"

    api_key: str = dataclasses.field(
        metadata={
            "required": True,
            "description": "Datadog Api Key",
            "hint": "https://docs.datadoghq.com/account_management/api-app-keys/#api-keys",
            "sensitive": True,
        }
    )
    app_key: str = dataclasses.field(
        metadata={
            "required": True,
            "description": "Datadog App Key",
            "hint": "https://docs.datadoghq.com/account_management/api-app-keys/#application-keys",
            "sensitive": True,
        }
    )


class DatadogProvider(BaseProvider):
    """
    Datadog provider class.
    """

    PROVIDER_SCOPES = [
        ProviderScope(
            name="events_read",
            description="Read events data.",
            mandatory=True,
            alias="Events Data Read",
        ),
        ProviderScope(
            name="monitors_read",
            description="Read monitors",
            mandatory=True,
            mandatory_for_webhook=True,
            documentation_url="https://docs.datadoghq.com/account_management/rbac/permissions/#monitors",
            alias="Monitors Read",
        ),
        ProviderScope(
            name="monitors_write",
            description="Write monitors",
            mandatory=False,
            mandatory_for_webhook=True,
            documentation_url="https://docs.datadoghq.com/account_management/rbac/permissions/#monitors",
            alias="Monitors Write",
        ),
        ProviderScope(
            name="create_webhooks",
            description="Create webhooks integrations",
            mandatory=False,
            mandatory_for_webhook=True,
            alias="Integrations Manage",
        ),
        ProviderScope(
            name="metrics_read",
            description="View custom metrics.",
            mandatory=False,
        ),
        ProviderScope(
            name="logs_read",
            description="Read log data.",
            mandatory=False,
            alias="Logs Read Data",
        ),
    ]
    PROVIDER_METHODS = [
        ProviderMethod(
            name="Mute a Monitor",
            func_name="mute_monitor",
            scopes=["monitors_write"],
            description="Mute a monitor",
            type="action",
        ),
        ProviderMethod(
            name="Unmute a Monitor",
            func_name="unmute_monitor",
            scopes=["monitors_write"],
            description="Unmute a monitor",
            type="action",
        ),
        ProviderMethod(
            name="Get Monitor Events",
            func_name="get_monitor_events",
            scopes=["events_read"],
            description="Get all events related to this monitor",
            type="view",
        ),
    ]
    FINGERPRINT_FIELDS = ["groups", "monitor_id"]
    WEBHOOK_PAYLOAD = json.dumps(
        {
            "body": "$EVENT_MSG",
            "last_updated": "$LAST_UPDATED",
            "event_type": "$EVENT_TYPE",
            "title": "$EVENT_TITLE",
            "severity": "$ALERT_PRIORITY",
            "alert_type": "$ALERT_TYPE",
            "alert_query": "$ALERT_QUERY",
            "alert_transition": "$ALERT_TRANSITION",
            "date": "$DATE",
            "scopes": "$ALERT_SCOPE",
            "org": {"id": "$ORG_ID", "name": "$ORG_NAME"},
            "url": "$LINK",
            "tags": "$TAGS",
            "id": "$ID",
            "monitor_id": "$ALERT_ID",
        }
    )

    def convert_to_seconds(s):
        seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return int(s[:-1]) * seconds_per_unit[s[-1]]

    def __init__(
        self, context_manager: ContextManager, provider_id: str, config: ProviderConfig
    ):
        super().__init__(context_manager, provider_id, config)
        self.configuration = Configuration(request_timeout=5)
        self.configuration.api_key["apiKeyAuth"] = self.authentication_config.api_key
        self.configuration.api_key["appKeyAuth"] = self.authentication_config.app_key
        # to be exposed
        self.to = None
        self._from = None

    def mute_monitor(
        self,
        monitor_id: str,
        groups: list = [],
        end: datetime.datetime = datetime.datetime.now() + datetime.timedelta(days=1),
    ):
        self.logger.info("Muting monitor", extra={"monitor_id": monitor_id, "end": end})
        if isinstance(end, str):
            end = datetime.datetime.fromisoformat(end)

        groups = ",".join(groups)
        if groups == "*":
            groups = ""

        with ApiClient(self.configuration) as api_client:
            endpoint = Endpoint(
                settings={
                    "auth": ["apiKeyAuth", "appKeyAuth", "AuthZ"],
                    "endpoint_path": "/api/v1/monitor/{monitor_id}/mute",
                    "response_type": (dict,),
                    "operation_id": "mute_monitor",
                    "http_method": "POST",
                    "version": "v1",
                },
                params_map={
                    "monitor_id": {
                        "required": True,
                        "openapi_types": (int,),
                        "attribute": "monitor_id",
                        "location": "path",
                    },
                    "scope": {
                        "openapi_types": (str,),
                        "attribute": "scope",
                        "location": "query",
                    },
                    "end": {
                        "openapi_types": (int,),
                        "attribute": "end",
                        "location": "query",
                    },
                },
                headers_map={
                    "accept": ["application/json"],
                    "content_type": ["application/json"],
                },
                api_client=api_client,
            )
            endpoint.call_with_http_info(
                monitor_id=int(monitor_id),
                end=int(end.timestamp()),
                scope=groups,
            )
        self.logger.info("Monitor muted", extra={"monitor_id": monitor_id})

    def unmute_monitor(
        self,
        monitor_id: str,
        groups: list = [],
    ):
        self.logger.info("Unmuting monitor", extra={"monitor_id": monitor_id})

        groups = ",".join(groups)

        with ApiClient(self.configuration) as api_client:
            endpoint = Endpoint(
                settings={
                    "auth": ["apiKeyAuth", "appKeyAuth", "AuthZ"],
                    "endpoint_path": "/api/v1/monitor/{monitor_id}/unmute",
                    "response_type": (dict,),
                    "operation_id": "mute_monitor",
                    "http_method": "POST",
                    "version": "v1",
                },
                params_map={
                    "monitor_id": {
                        "required": True,
                        "openapi_types": (int,),
                        "attribute": "monitor_id",
                        "location": "path",
                    },
                    "scope": {
                        "openapi_types": (str,),
                        "attribute": "scope",
                        "location": "query",
                    },
                },
                headers_map={
                    "accept": ["application/json"],
                    "content_type": ["application/json"],
                },
                api_client=api_client,
            )
            endpoint.call_with_http_info(
                monitor_id=int(monitor_id),
                scope=groups,
            )
        self.logger.info("Monitor unmuted", extra={"monitor_id": monitor_id})

    def get_monitor_events(self, monitor_id: str):
        self.logger.info("Getting monitor events", extra={"monitor_id": monitor_id})
        with ApiClient(self.configuration) as api_client:
            # tb: when it's out of beta, we should move to api v2
            api = EventsApi(api_client)
            end = datetime.datetime.now()
            # tb: we can make timedelta configurable by the user if we want
            start = datetime.datetime.now() - datetime.timedelta(days=1)
            results = api.list_events(
                start=int(start.timestamp()),
                end=int(end.timestamp()),
                tags="source:alert",
            )
            # Filter out events that are related to this monitor only
            # tb: We might want to exclude some fields from event.to_dict() but let's wait for user feedback
            results = [
                event.to_dict()
                for event in results.get("events", [])
                if str(event.monitor_id) == str(monitor_id)
            ]
            self.logger.info(
                "Monitor events retrieved", extra={"monitor_id": monitor_id}
            )
            return results

    def dispose(self):
        """
        Dispose the provider.
        """
        pass

    def validate_config(self):
        """
        Validates required configuration for Datadog provider.

        """
        self.authentication_config = DatadogProviderAuthConfig(
            **self.config.authentication
        )

    def validate_scopes(self):
        scopes = {}
        self.logger.info("Validating scopes")
        with ApiClient(self.configuration) as api_client:
            for scope in self.PROVIDER_SCOPES:
                try:
                    if scope.name == "monitors_read":
                        api = MonitorsApi(api_client)
                        api.list_monitors()
                    elif scope.name == "monitors_write":
                        api = MonitorsApi(api_client)
                        body = Monitor(
                            name="Example-Monitor",
                            type=MonitorType.RUM_ALERT,
                            query='formula("1 * 100").last("15m") >= 200',
                            message="some message Notify: @hipchat-channel",
                            tags=[
                                "test:examplemonitor",
                                "env:ci",
                            ],
                            priority=3,
                            options=MonitorOptions(
                                thresholds=MonitorThresholds(
                                    critical=200,
                                ),
                                variables=[],
                            ),
                        )
                        monitor = api.create_monitor(body)
                        api.delete_monitor(monitor.id)
                    elif scope.name == "create_webhooks":
                        api = WebhooksIntegrationApi(api_client)
                        # We check if we have permissions to query webhooks, this means we have the create_webhooks scope
                        try:
                            api.create_webhooks_integration(
                                body={
                                    "name": "keep-webhook-scope-validation",
                                    "url": "https://example.com",
                                }
                            )
                            # for some reason create_webhooks does not allow to delete: api.delete_webhooks_integration(webhook_name), no scope for deletion
                        except ApiException as e:
                            # If it's something different from 403 it means we have access! (for example, already exists because we created it once)
                            if e.status == 403:
                                raise e
                    elif scope.name == "metrics_read":
                        api = MetricsApi(api_client)
                        api.query_metrics(
                            query="system.cpu.idle{*}",
                            _from=int((datetime.datetime.now()).timestamp()),
                            to=int(datetime.datetime.now().timestamp()),
                        )
                    elif scope.name == "logs_read":
                        self._query(
                            query="*",
                            timeframe="1h",
                            query_type="logs",
                        )
                    elif scope.name == "events_read":
                        api = EventsApi(api_client)
                        end = datetime.datetime.now()
                        start = datetime.datetime.now() - datetime.timedelta(hours=1)
                        api.list_events(
                            start=int(start.timestamp()), end=int(end.timestamp())
                        )
                except ApiException as e:
                    # API failed and it means we're probably lacking some permissions
                    # perhaps we should check if status code is 403 and otherwise mark as valid?
                    self.logger.warning(
                        f"Failed to validate scope {scope.name}",
                        extra={"reason": e.reason, "code": e.status},
                    )
                    scopes[scope.name] = str(e.reason)
                    continue
                scopes[scope.name] = True
        self.logger.info("Scopes validated", extra=scopes)
        return scopes

    def expose(self):
        return {
            "to": int(self.to.timestamp()) * 1000,
            "from": int(self._from.timestamp()) * 1000,
        }

    def _query(self, query="", timeframe="", query_type="", **kwargs: dict):
        timeframe_in_seconds = DatadogProvider.convert_to_seconds(timeframe)
        self.to = datetime.datetime.fromtimestamp(time.time())
        self._from = datetime.datetime.fromtimestamp(
            time.time() - (timeframe_in_seconds)
        )
        if query_type == "logs":
            with ApiClient(self.configuration) as api_client:
                api = LogsApi(api_client)
                results = api.list_logs(
                    body={
                        "query": query,
                        "time": {
                            "_from": self._from,
                            "to": self.to,
                        },
                    }
                )
        elif query_type == "metrics":
            with ApiClient(self.configuration) as api_client:
                api = MetricsApi(api_client)
                results = api.query_metrics(
                    query=query,
                    _from=time.time() - (timeframe_in_seconds * 1000),
                    to=time.time(),
                )
        return results

    def get_alerts_configuration(self, alert_id: str | None = None):
        with ApiClient(self.configuration) as api_client:
            api = MonitorsApi(api_client)
            try:
                monitors = api.list_monitors()
            except Exception as e:
                raise GetAlertException(message=str(e), status_code=e.status)
            monitors = [
                json.dumps(monitor.to_dict(), default=str) for monitor in monitors
            ]
            if alert_id:
                monitors = list(
                    filter(lambda monitor: monitor["id"] == alert_id, monitors)
                )
        return monitors

    @staticmethod
    def __get_parsed_severity(priority):
        if priority == "P1":
            return "critical"
        elif priority == "P2":
            return "high"
        elif priority == "P3":
            return "medium"
        elif priority == "P4":
            return "low"

    def _get_alerts(self) -> list[AlertDto]:
        formatted_alerts = []
        with ApiClient(self.configuration) as api_client:
            # tb: when it's out of beta, we should move to api v2
            # https://docs.datadoghq.com/api/latest/events/
            monitors_api = MonitorsApi(api_client)
            all_monitors = {
                monitor.id: monitor
                for monitor in monitors_api.list_monitors(with_downtimes=True)
            }
            api = EventsApi(api_client)
            end = datetime.datetime.now()
            # tb: we can make timedelta configurable by the user if we want
            start = datetime.datetime.now() - datetime.timedelta(days=30)
            results = api.list_events(
                start=int(start.timestamp()),
                end=int(end.timestamp()),
                tags="source:alert",
            )
            events = results.get("events", [])
            for event in events:
                try:
                    tags = {
                        k: v
                        for k, v in map(
                            lambda tag: tag.split(":", 1),
                            [tag for tag in event.tags if ":" in tag],
                        )
                    }
                    severity, status, title = event.title.split(" ", 2)
                    severity = self.__get_parsed_severity(
                        severity.lstrip("[").rstrip("]")
                    )
                    status = status.lstrip("[").rstrip("]")
                    received = datetime.datetime.fromtimestamp(
                        event.get("date_happened")
                    )
                    monitor = all_monitors.get(event.monitor_id)
                    is_muted = any(
                        [
                            downtime
                            for downtime in monitor.matching_downtimes
                            if downtime.groups == event.monitor_groups
                            or downtime.scope == ["*"]
                        ]
                    )
                    alert = AlertDto(
                        id=event.id,
                        name=title,
                        status=status if not is_muted else "Muted",
                        lastReceived=received.isoformat(),
                        severity=severity,
                        message=event.text,
                        monitor_id=event.monitor_id,
                        # tb: sometimes referred as scopes
                        groups=event.monitor_groups,
                        source=["datadog"],
                        tags=tags,
                        created_by=monitor.creator.email
                        if monitor and monitor.creator
                        else None,
                    )
                    alert.fingerprint = self.get_alert_fingerprint(
                        alert, self.fingerprint_fields
                    )
                    formatted_alerts.append(alert)
                except Exception as e:
                    self.logger.exception(
                        "Could not parse alert event",
                        extra={"event_id": event.id, "monitor_id": event.monitor_id},
                    )
                    continue
        return formatted_alerts

    def setup_webhook(
        self, tenant_id: str, keep_api_url: str, api_key: str, setup_alerts: bool = True
    ):
        self.logger.info("Creating or updating webhook")
        webhook_name = f"{DatadogProviderAuthConfig.KEEP_DATADOG_WEBHOOK_INTEGRATION_NAME}-{tenant_id}"
        with ApiClient(self.configuration) as api_client:
            api = WebhooksIntegrationApi(api_client)
            try:
                webhook = api.get_webhooks_integration(webhook_name=webhook_name)
                if webhook.url != keep_api_url:
                    api.update_webhooks_integration(
                        webhook.name,
                        body={
                            "url": keep_api_url,
                            "custom_headers": json.dumps(
                                {
                                    "Content-Type": "application/json",
                                    "X-API-KEY": api_key,
                                }
                            ),
                            "payload": DatadogProvider.WEBHOOK_PAYLOAD,
                        },
                    )
                    self.logger.info(
                        "Webhook updated",
                    )
            except (NotFoundException, ForbiddenException):
                try:
                    webhook = api.create_webhooks_integration(
                        body={
                            "name": webhook_name,
                            "url": keep_api_url,
                            "custom_headers": json.dumps(
                                {
                                    "Content-Type": "application/json",
                                    "X-API-KEY": api_key,
                                }
                            ),
                            "encode_as": "json",
                            "payload": DatadogProvider.WEBHOOK_PAYLOAD,
                        }
                    )
                    self.logger.info("Webhook created")
                except ApiException as exc:
                    if "Webhook already exists" in exc.body.get("errors"):
                        self.logger.info(
                            "Webhook already exists when trying to add, updating"
                        )
                        try:
                            api.update_webhooks_integration(
                                webhook_name,
                                body={
                                    "url": keep_api_url,
                                    "custom_headers": json.dumps(
                                        {
                                            "Content-Type": "application/json",
                                            "X-API-KEY": api_key,
                                        }
                                    ),
                                    "payload": DatadogProvider.WEBHOOK_PAYLOAD,
                                },
                            )
                        except ApiException:
                            self.logger.exception("Failed to update webhook")
                    else:
                        raise
            self.logger.info("Webhook created or updated")
            if setup_alerts:
                self.logger.info("Updating monitors")
                api = MonitorsApi(api_client)
                monitors = api.list_monitors()
                for monitor in monitors:
                    try:
                        self.logger.info(
                            "Updating monitor",
                            extra={
                                "monitor_id": monitor.id,
                                "monitor_name": monitor.name,
                            },
                        )
                        monitor_message = monitor.message
                        if f"@webhook-{webhook_name}" not in monitor_message:
                            monitor_message = (
                                f"{monitor_message} @webhook-{webhook_name}"
                            )
                            api.update_monitor(
                                monitor.id, body={"message": monitor_message}
                            )
                            self.logger.info(
                                "Monitor updated",
                                extra={
                                    "monitor_id": monitor.id,
                                    "monitor_name": monitor.name,
                                },
                            )
                    except Exception:
                        self.logger.exception(
                            "Could not update monitor",
                            extra={
                                "monitor_id": monitor.id,
                                "monitor_name": monitor.name,
                            },
                        )
                self.logger.info("Monitors updated")

    def format_alert(event: dict) -> AlertDto:
        tags_list = event.get("tags", "").split(",")
        tags_list.remove("monitor")
        tags = {k: v for k, v in map(lambda tag: tag.split(":"), tags_list)}
        event_time = datetime.datetime.fromtimestamp(
            int(event.get("last_updated")) / 1000
        )
        severity, status, title = event.get("title").split(" ", 2)
        url = event.pop("url", None)

        # https://docs.datadoghq.com/integrations/webhooks/#variables
        groups = event.get("scopes", "")
        if not groups:
            groups = ["*"]
        else:
            groups = groups.split(",")

        alert = AlertDto(
            id=event.get("id"),
            name=title,
            status=status.lstrip("[").rstrip("]"),
            lastReceived=str(event_time),
            source=["datadog"],
            message=event.get("body"),
            groups=groups,
            severity=DatadogProvider.__get_parsed_severity(
                event.get("severity", severity)
            ),
            url=url,
            tags=tags,
            monitor_id=event.get("monitor_id"),
        )
        alert.fingerprint = DatadogProvider.get_alert_fingerprint(
            alert, DatadogProvider.FINGERPRINT_FIELDS
        )
        return alert

    def deploy_alert(self, alert: dict, alert_id: str | None = None):
        body = Monitor(**alert)
        with ApiClient(self.configuration) as api_client:
            api_instance = MonitorsApi(api_client)
            try:
                response = api_instance.create_monitor(body=body)
            except Exception as e:
                raise Exception({"message": e.body["errors"][0]})
        return response

    def get_logs(self, limit: int = 5) -> list:
        # Logs from the last 7 days
        timeframe_in_seconds = DatadogProvider.convert_to_seconds("7d")
        _from = datetime.datetime.fromtimestamp(time.time() - (timeframe_in_seconds))
        to = datetime.datetime.fromtimestamp(time.time())
        with ApiClient(self.configuration) as api_client:
            api = LogsApi(api_client)
            results = api.list_logs(
                body={"limit": limit, "time": {"_from": _from, "to": to}}
            )
        return [log.to_dict() for log in results["logs"]]

    @staticmethod
    def get_alert_schema():
        return DatadogAlertFormatDescription.schema()


if __name__ == "__main__":
    # Output debug messages
    import logging

    logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler()])
    context_manager = ContextManager(
        tenant_id="singletenant",
        workflow_id="test",
    )
    # Load environment variables
    import os

    api_key = os.environ.get("DATADOG_API_KEY")
    app_key = os.environ.get("DATADOG_APP_KEY")

    provider_config = {
        "authentication": {"api_key": api_key, "app_key": app_key},
    }
    provider = ProvidersFactory.get_provider(
        context_manager=context_manager,
        provider_id="datadog-keephq",
        provider_type="datadog",
        provider_config=provider_config,
    )
    result = provider._get_alerts()
    print(result)
