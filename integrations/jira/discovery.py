import logging
from typing import Any, Dict, List, Optional, Union

from integrations.jira.client import JiraClient

logger = logging.getLogger(__name__)


class JiraDiscoveryError(Exception):
    """Raised when Jira project, service desk, or request type cannot be discovered."""
    pass


class JiraDiscovery:
    """Dynamically discovers Jira Service Management projects, service desks, request types, and field schemas."""

    def __init__(self, client: Optional[JiraClient] = None):
        self.client = client or JiraClient()
        self._cache: Dict[str, Any] = {}

    def discover_project(self, project_key: Optional[str] = None) -> Dict[str, Any]:
        """Dynamically resolve project details using JIRA_PROJECT_KEY."""
        key = (project_key or self.client.config.project_key).strip().upper()
        cache_key = f"project:{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = self.client.get_project(key)
        project_info = {
            "id": str(data.get("id")),
            "key": data.get("key"),
            "name": data.get("name"),
            "projectTypeKey": data.get("projectTypeKey"),
        }
        self._cache[cache_key] = project_info
        return project_info

    def discover_service_desk(self, project_key: Optional[str] = None) -> Dict[str, Any]:
        """Dynamically discover the service desk associated with the target project."""
        project = self.discover_project(project_key)
        target_project_id = project["id"]
        target_project_key = project["key"]

        cache_key = f"servicedesk:{target_project_key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        desks = self.client.get_service_desks()
        for desk in desks:
            if str(desk.get("projectId")) == target_project_id or desk.get("projectKey") == target_project_key:
                sd_info = {
                    "id": str(desk.get("id")),
                    "projectId": str(desk.get("projectId")),
                    "projectKey": desk.get("projectKey"),
                    "projectName": desk.get("projectName"),
                }
                self._cache[cache_key] = sd_info
                return sd_info

        raise JiraDiscoveryError(
            f"No Jira Service Desk found for project '{target_project_key}' (ID: {target_project_id})."
        )

    def discover_incident_request_type(self, service_desk_id: Union[int, str]) -> Dict[str, Any]:
        """Dynamically find the Incident customer request type for the service desk."""
        sd_id = str(service_desk_id)
        cache_key = f"requesttype:{sd_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        request_types = self.client.get_request_types(sd_id)
        if not request_types:
            raise JiraDiscoveryError(f"No customer request types configured in Service Desk ID {sd_id}.")

        # Identify Incident request type by name or description
        incident_rt = None
        for rt in request_types:
            name = (rt.get("name") or "").lower()
            desc = (rt.get("description") or "").lower()

            # Specific match for incident reporting
            if "report a system problem" in name or "incident" in name or "system problem" in desc:
                incident_rt = rt
                break

        # Fallback to first available request type if no specific incident title matched
        if not incident_rt:
            incident_rt = request_types[0]
            logger.warning(
                "Could not find exact 'Report a system problem' request type. Using: %s",
                incident_rt.get("name"),
            )

        rt_info = {
            "id": str(incident_rt.get("id")),
            "name": incident_rt.get("name"),
            "description": incident_rt.get("description"),
            "serviceDeskId": sd_id,
        }
        self._cache[cache_key] = rt_info
        return rt_info

    def discover_request_type_fields(
        self,
        service_desk_id: Union[int, str],
        request_type_id: Union[int, str],
    ) -> Dict[str, Any]:
        """Discover required and optional fields along with allowed options (Urgency/Impact)."""
        sd_id = str(service_desk_id)
        rt_id = str(request_type_id)
        cache_key = f"fields:{sd_id}:{rt_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        raw_data = self.client.get_request_type_fields(sd_id, rt_id)
        raw_fields: List[Dict[str, Any]] = raw_data.get("requestTypeFields", [])

        required_fields: List[str] = []
        optional_fields: List[str] = []
        field_id_map: Dict[str, str] = {}
        urgency_options: Dict[str, str] = {}
        impact_options: Dict[str, str] = {}

        for f in raw_fields:
            field_id = f.get("fieldId", "")
            field_name = (f.get("name") or "").lower()
            is_required = f.get("required", False)

            if is_required:
                required_fields.append(field_id)
            else:
                optional_fields.append(field_id)

            # Map semantic field names dynamically
            if field_id == "summary" or "summar" in field_name:
                field_id_map["summary"] = field_id
            elif field_id == "description" or "describe" in field_name:
                field_id_map["description"] = field_id
            elif "urgent" in field_name or "urgency" in field_name:
                field_id_map["urgency"] = field_id
                for opt in f.get("validValues", []):
                    lbl = opt.get("label") or opt.get("value")
                    val = opt.get("value") or opt.get("id")
                    if lbl and val:
                        urgency_options[lbl.strip()] = str(val)
            elif "impact" in field_name:
                field_id_map["impact"] = field_id
                for opt in f.get("validValues", []):
                    lbl = opt.get("label") or opt.get("value")
                    val = opt.get("value") or opt.get("id")
                    if lbl and val:
                        impact_options[lbl.strip()] = str(val)
            elif "service" in field_name:
                field_id_map["affected_services"] = field_id
            elif "attachment" in field_id or "attach" in field_name:
                field_id_map["attachment"] = field_id

        result = {
            "serviceDeskId": sd_id,
            "requestTypeId": rt_id,
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "field_id_map": field_id_map,
            "urgency_options": urgency_options,
            "impact_options": impact_options,
            "raw_fields": raw_fields,
        }
        self._cache[cache_key] = result
        return result

    def discover_incident_metadata(self) -> Dict[str, Any]:
        """Execute end-to-end dynamic discovery of all incident metadata."""
        project = self.discover_project()
        service_desk = self.discover_service_desk(project["key"])
        request_type = self.discover_incident_request_type(service_desk["id"])
        fields = self.discover_request_type_fields(service_desk["id"], request_type["id"])

        return {
            "project": project,
            "service_desk": service_desk,
            "request_type": request_type,
            "fields": fields,
        }
