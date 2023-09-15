hqDefine("geospatial/js/geospatial_map", [
    "jquery",
    "hqwebapp/js/initial_page_data",
    "knockout",
    "hqwebapp/js/bootstrap3/alert_user",
], function (
    $,
    initialPageData,
    ko,
    alert_user
) {
    const defaultMarkerColor = "#808080"; // Gray
    const defaultUserMarkerColor = "#0e00ff"; // Blue
    const selectedMarkerColor = "#00FF00"; // Green
    const selectedUserMarkerColor = "#0b940d"; // Dark Green
    var saveGeoJSONUrl = initialPageData.reverse('geo_polygon');

    function mapItemModel(dataId, dataItem, marker, markerColors) {
        'use strict';
        var self = {};
        self.dataId = dataId;
        self.dataItem = dataItem;
        self.marker = marker;
        self.selectCssId = "select" + dataId;
        self.isSelected = ko.observable(false);
        self.markerColors = markerColors;

        function changeMarkerColor(selectedCase, newColor) {
            let marker = selectedCase.marker;
            let element = marker.getElement();
            let svg = element.getElementsByTagName("svg")[0];
            let path = svg.getElementsByTagName("path")[0];
            path.setAttribute("fill", newColor);
        }

        self.isSelected.subscribe(function () {
            var color = self.isSelected() ? self.markerColors.selected : self.markerColors.default;
            changeMarkerColor(self, color);
        });
        return self;
    }

    function showMapControls(state) {
        $("#geospatial-map").toggle(state);
        $("#case-buttons").toggle(state);
        $("#mapControls").toggle(state);
    }

    $(function () {
        // Global var
        var map;

        var caseModels = ko.observableArray([]);
        var userModels = ko.observableArray([]);
        var selectedCases = ko.computed(function () {
            return caseModels().filter(function (currCase) {
                return currCase.isSelected();
            });
        });
        var selectedUsers = ko.computed(function () {
            return userModels().filter(function (currUser) {
                return currUser.isSelected();
            });
        });

        function filterMapItemsInPolygon(polygonFeature) {
            _.values(caseModels()).filter(function (currCase) {
                if (currCase.dataItem.coordinates) {
                    currCase.isSelected(isMapItemInPolygon(polygonFeature, currCase.dataItem.coordinates));
                }
            });
            _.values(userModels()).filter(function (currUser) {
                if (currUser.dataItem.coordinates) {
                    currUser.isSelected(isMapItemInPolygon(polygonFeature, currUser.dataItem.coordinates));
                }
            });
        }

        function isMapItemInPolygon(polygonFeature, coordinates) {
            // Might be 0 if a user deletes a point from a three-point polygon
            if (!polygonFeature.geometry.coordinates.length) {
                return false;
            }
            const coordinatesArr = [coordinates.lng, coordinates.lat];
            const point = turf.point(coordinatesArr);
            return turf.booleanPointInPolygon(point, polygonFeature.geometry);
        }

        var loadMapBox = function (centerCoordinates) {
            'use strict';

            var self = {};
            let clickedMarker;
            mapboxgl.accessToken = initialPageData.get('mapbox_access_token');

            if (!centerCoordinates) {
                centerCoordinates = [-91.874, 42.76]; // should be domain specific
            }

            const map = new mapboxgl.Map({
                container: 'geospatial-map', // container ID
                style: 'mapbox://styles/mapbox/streets-v12', // style URL
                center: centerCoordinates, // starting position [lng, lat]
                zoom: 12,
                attribution: '© <a href="https://www.mapbox.com/about/maps/">Mapbox</a> ©' +
                             ' <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            });

            const draw = new MapboxDraw({
                // API: https://github.com/mapbox/mapbox-gl-draw/blob/main/docs/API.md
                displayControlsDefault: false,
                boxSelect: true, // enables box selection
                controls: {
                    polygon: true,
                    trash: true,
                },
            });

            map.addControl(draw);

            map.on("draw.update", function (e) {
                var selectedFeatures = e.features;

                // Check if any features are selected
                if (!selectedFeatures.length) {
                    return;
                }
                var selectedFeature = selectedFeatures[0];

                if (selectedFeature.geometry.type === 'Polygon') {
                    filterMapItemsInPolygon(selectedFeature);
                }
            });

            map.on('draw.selectionchange', function (e) {
                // See https://github.com/mapbox/mapbox-gl-draw/blob/main/docs/API.md#drawselectionchange
                var selectedFeatures = e.features;
                if (!selectedFeatures.length) {
                    return;
                }

                // Check if any features are selected
                var selectedFeature = selectedFeatures[0];
                // Update this logic if we need to support case filtering by selecting multiple polygons

                if (selectedFeature.geometry.type === 'Polygon') {
                    // Now that we know we selected a polygon, we need to check which markers are inside
                    filterMapItemsInPolygon(selectedFeature);
                }
            });

            function getCoordinates(event) {
                return event.lngLat;
            }

            // We should consider refactoring and splitting the below out to a new JS file
            function moveMarkerToClickedCoordinate(coordinates) {
                if (clickedMarker !== null) {
                    clickedMarker.remove();
                }
                if (draw.getMode() === 'draw_polygon') {
                    // It's weird moving the marker around with the ploygon
                    return;
                }
                clickedMarker = new mapboxgl.Marker({color: "FF0000", draggable: true});
                clickedMarker.setLngLat(coordinates);
                clickedMarker.addTo(map);
            }

            self.getMapboxDrawInstance = function () {
                return draw;
            };

            self.getMapboxInstance = function () {
                return map;
            };

            self.removeCaseMarkers = function () {
                _.each(caseModels(), function (currCase) {
                    if (currCase.marker) {
                        currCase.marker.remove();
                    }
                });
                caseModels([]);
            };

            self.removeUserMarkers = function () {
                _.each(userModels(), function (currUser) {
                    if (currUser.marker) {
                        currUser.marker.remove();
                    }
                });
                userModels([]);
            };

            self.addCaseMarkersToMap = function (rawCases) {
                const caseColors = {
                    'default': defaultMarkerColor,
                    'selected': selectedMarkerColor,
                };

                _.forEach(rawCases, function (element, caseId) {
                    const coordinates = element.coordinates;
                    if (coordinates && coordinates.lat && coordinates.lng) {
                        const mapItemInstance = self.addMarker(caseId, element, caseColors);
                        caseModels.push(mapItemInstance);
                    }
                });
            };

            self.addUserMarkersToMap = function (rawUsers) {
                const userColors = {
                    'default': defaultUserMarkerColor,
                    'selected': selectedUserMarkerColor,
                };

                _.forEach(rawUsers, function (element, userId) {
                    const coordinates = element.coordinates;
                    if (coordinates && coordinates.lat && coordinates.lng) {
                        const mapItemInstance = self.addMarker(userId, element, userColors);
                        userModels.push(mapItemInstance);
                    }
                });
            };

            self.addMarker = function (dataId, dataItem, colors) {
                const coordinates = dataItem.coordinates;
                // Create the marker
                const marker = new mapboxgl.Marker({ color: colors.default, draggable: false });
                marker.setLngLat(coordinates);

                // Add the marker to the map
                marker.addTo(map);

                let popupDiv = document.createElement("div");
                popupDiv.setAttribute("data-bind", "template: 'select-case'");

                let popup = new mapboxgl.Popup({ offset: 25, anchor: "bottom" })
                    .setLngLat(coordinates)
                    .setDOMContent(popupDiv);

                marker.setPopup(popup);

                const markerDiv = marker.getElement();
                // Show popup on hover
                markerDiv.addEventListener('mouseenter', () => marker.togglePopup());

                // Hide popup if mouse leaves marker and popup
                var addLeaveEvent = function (fromDiv, toDiv) {
                    fromDiv.addEventListener('mouseleave', function () {
                        setTimeout(function () {
                            if (!$(toDiv).is(':hover')) {
                                // mouse left toDiv as well
                                marker.togglePopup();
                            }
                        }, 100);
                    });
                };
                addLeaveEvent(markerDiv, popupDiv);
                addLeaveEvent(popupDiv, markerDiv);

                const mapItemInstance = new mapItemModel(dataId, dataItem, marker, colors);
                $(popupDiv).koApplyBindings(mapItemInstance);

                return mapItemInstance;
            };

            ko.applyBindings({'caseModels': caseModels, 'selectedCases': selectedCases}, $("#case-modals")[0]);
            // Handle click events here
            map.on('click', (event) => {
                let coordinates = getCoordinates(event);
            });
            return self;
        };

        var saveGeoJson = function (drawInstance, mapControlsModelInstance) {
            var data = drawInstance.getAll();

            if (data.features.length) {
                let name = window.prompt(gettext("Name of the Area"));
                data['name'] = name;

                $.ajax({
                    type: 'post',
                    url: saveGeoJSONUrl,
                    dataType: 'json',
                    data: JSON.stringify({'geo_json': data}),
                    contentType: "application/json; charset=utf-8",
                    success: function (ret) {
                        delete data.name;
                        // delete drawn area
                        drawInstance.deleteAll();
                        mapControlsModelInstance.savedPolygons.push(
                            savedPolygon({
                                name: name,
                                id: ret.id,
                                geo_json: data
                            })
                        );
                        // redraw using mapControlsModelInstance
                        mapControlsModelInstance.selectedPolygon(ret.id);
                    }
                });
            }
        };

        function savedPolygon(polygon) {
            var self = {};
            self.text = polygon.name;
            self.id = polygon.id;
            self.geoJson = polygon.geo_json;
            return self;
        }

        var mapControlsModel = function () {
            'use strict';
            var self = {};
            var mapboxinstance = map.getMapboxInstance();
            self.btnSaveDisabled = ko.observable(true);
            self.btnExportDisabled = ko.observable(true);

            // initial saved polygons
            self.savedPolygons = ko.observableArray();
            _.each(initialPageData.get('saved_polygons'), function (polygon) {
                self.savedPolygons.push(savedPolygon(polygon));
            });
            // Keep track of the Polygon selected by the user
            self.selectedPolygon = ko.observable();
            // Keep track of the Polygon displayed
            self.activePolygon = ko.observable();

            // On selection, add the polygon to the map
            self.selectedPolygon.subscribe(function (value) {
                var polygonObj = self.savedPolygons().find(
                    function (o) { return o.id == self.selectedPolygon(); }
                );
                // Clear existing polygon
                if (self.activePolygon()) {
                    mapboxinstance.removeLayer(self.activePolygon());
                    mapboxinstance.removeSource(self.activePolygon());
                }
                if (value !== undefined) {
                    // Add selected polygon
                    mapboxinstance.addSource(
                        String(polygonObj.id),
                        {'type': 'geojson', 'data':polygonObj.geoJson}
                    );
                    mapboxinstance.addLayer({
                        'id': String(polygonObj.id),
                        'type': 'fill',
                        'source': String(polygonObj.id),
                        'layout': {},
                        'paint': {
                            'fill-color': '#0080ff',
                            'fill-opacity': 0.5
                        }
                    });
                    polygonObj.geoJson.features.forEach(
                        filterMapItemsInPolygon
                    );
                    self.btnExportDisabled(false);
                    self.btnSaveDisabled(true);
                }
                // Mark as active polygon
                self.activePolygon(self.selectedPolygon());
            });

            var mapHasPolygons = function () {
                var drawnFeatures = map.getMapboxDrawInstance().getAll().features;
                if (!drawnFeatures.length) {
                    return false;
                }
                return drawnFeatures.some(function (feature) {
                    return feature.geometry.type === "Polygon";
                });
            };

            mapboxinstance.on('draw.delete', function () {
                self.btnSaveDisabled(!mapHasPolygons());
            });

            mapboxinstance.on('draw.create', function () {
                self.btnSaveDisabled(!mapHasPolygons());
            });

            self.exportGeoJson = function(){
                var exportButton = $("#btnExportDrawnArea");
                var selectedPolygon = self.savedPolygons().find(
                    function (o) { return o.id == self.selectedPolygon(); }
                );
                if (selectedPolygon) {
                    var convertedData = 'text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(selectedPolygon.geoJson));
                    exportButton.attr('href', 'data:' + convertedData);
                    exportButton.attr('download','data.geojson');
                }
            }

            return self;
        };

        function initMapControls() {
            // Assumes `map` var is initialized
            var $mapControlDiv = $("#mapControls");
            var mapControlsModelInstance = mapControlsModel();
            if ($mapControlDiv.length) {
                ko.cleanNode($mapControlDiv[0]);
                $mapControlDiv.koApplyBindings(mapControlsModelInstance);
            }

            var $saveDrawnArea = $("#btnSaveDrawnArea");
            $saveDrawnArea.click(function(e) {
                if (map) {
                    saveGeoJson(map.getMapboxDrawInstance(), mapControlsModelInstance);
                }
            });

            var $exportDrawnArea = $("#btnExportDrawnArea");
            $exportDrawnArea.click(function(e) {
                if (map) {
                    mapControlsModelInstance.exportGeoJson()
                }
            });
        };

        var missingGPSModel = function(cases) {
            this.casesWithoutGPS = ko.observable(cases);
        };
        function loadCases(caseData) {
            map.removeCaseMarkers();
            var casesWithGPS = caseData.filter(function (item) {
                return item[1] !== null;
            });
            // Index by case_id
            var casesById = _.object(_.map(casesWithGPS, function (item) {
                if (item[1]) {
                    return [item[0], {'coordinates': item[1], 'link': item[2]}];
                }
            }));
            map.addCaseMarkersToMap(casesById, defaultMarkerColor);

            var $missingCasesDiv = $("#missing-gps-cases");
            var casesWithoutGPS = caseData.filter(function (item) {
                return item[1] === null;
            });
            casesWithoutGPS = _.map(casesWithoutGPS, function (item) {return {"link": item[2]};});
            // Don't re-apply if this is the next page of the pagination
            if (ko.dataFor($missingCasesDiv[0]) === undefined) {
                $missingCasesDiv.koApplyBindings(missingGPSModelInstance);
                missingGPSModelInstance.casesWithoutGPS(casesWithoutGPS);
            }
            missingGPSModelInstance.casesWithoutGPS(casesWithoutGPS);
        }

        $(document).ajaxComplete(function (event, xhr, settings) {
            const isAfterReportLoad = settings.url.includes('geospatial/async/case_management_map/');
            // This indicates clicking Apply button or initial page load
            if (isAfterReportLoad) {
                map = loadMapBox();
                initMapControls();
                // Hide controls until data is displayed
                showMapControls(false);
                return;
            }

            // This indicates that report data is fetched either after apply or after pagination
            const isAfterDataLoad = settings.url.includes('geospatial/json/case_management_map/');
            if (!isAfterDataLoad) {
                return;
            }
            isDataNeverFetched = true;
            showMapControls(true);
            // Hide the datatable rows but not the pagination bar
            $('.dataTables_scroll').hide();

            if (xhr.responseJSON.aaData.length && map) {
                loadCases(xhr.responseJSON.aaData);
            }
        });
    });
});
