"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.sendAnalyticsEvent = void 0;
const posthog_node_1 = require("posthog-node");
const os_1 = __importDefault(require("os"));
const crypto_1 = require("crypto");
const ci_info_1 = __importDefault(require("ci-info"));
const is_docker_1 = __importDefault(require("is-docker"));
const conf_1 = __importDefault(require("conf"));
const config = new conf_1.default();
if (!config.get('uid'))
    config.set('uid', (0, crypto_1.randomUUID)());
const uid = config.get('uid');
const posthog = new posthog_node_1.PostHog('phc_SIwnNDitjnc44ozMtjud1Uz1wXb4cgM63MhtWy1mL2O', { host: 'https://eu.posthog.com' });
function sendAnalyticsEvent() {
    if (!process.env.STEPCI_DISABLE_ANALYTICS) {
        posthog.capture({
            distinctId: uid,
            event: 'ping',
            properties: {
                os: os_1.default.type(),
                node: process.version,
                version: '2.5.x',
                command: process.argv.slice(2)[0],
                environment: ci_info_1.default.isCI ? ci_info_1.default.name : (0, is_docker_1.default)() ? 'Docker' : 'Local'
            }
        });
    }
}
exports.sendAnalyticsEvent = sendAnalyticsEvent;
process.on('beforeExit', () => posthog.shutdown());
